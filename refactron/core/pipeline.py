"""Pipeline orchestration for automated and session-based flows."""

import logging
from collections import defaultdict
from pathlib import Path
import time
from typing import Optional, Union, List, Dict, Any

from refactron.core.config import RefactronConfig
from refactron.core.refactron import Refactron
from refactron.core.analysis_result import AnalysisResult
from refactron.core.models import CodeIssue
from refactron.autofix.engine import AutoFixEngine
from refactron.core.pipeline_session import PipelineSession
from refactron.core.backup import BackupRollbackSystem

# Configure logging
logger = logging.getLogger(__name__)


class RefactronPipeline:
    """Automated pipeline execution for session-based and CI/CD flows."""

    def __init__(
        self,
        project_root: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize the pipeline.

        Args:
            project_root: Optional root directory of the project.
            config_path: Optional explicit configuration path.
        """
        self.project_root = Path(project_root) if project_root else None
        self.config_path = Path(config_path) if config_path else None

        self._config = self._load_config()
        # Enforce pipeline default behavior (full scan) unless overridden later
        self._config.enable_incremental_analysis = False
        self.refactron = Refactron(self._config)
        self.autofix_engine = AutoFixEngine()
        self._fixer_cache = {}
        self.session = PipelineSession()

    def _load_config(self) -> RefactronConfig:
        if self.config_path and self.config_path.exists():
            return RefactronConfig.from_file(self.config_path)

        root = self.project_root or Path.cwd()
        yaml_path = root / ".refactron.yaml"
        if yaml_path.exists():
            return RefactronConfig.from_file(yaml_path)
        return RefactronConfig.default()

    def analyze(
        self, target: Union[str, Path], use_incremental: Optional[bool] = None
    ) -> AnalysisResult:
        """
        Run analysis as part of a pipeline flow.

        Pipeline-only overrides:
        - `enable_incremental_analysis` is forced to False by default to guarantee
          a fully fresh, reproducible analysis in CI/CD or pipeline environments.

        Args:
            target: Path to file or directory to analyze.
            use_incremental: Optional override to enable incremental analysis.

        Returns:
            AnalysisResult containing issues and metrics.
        """
        if use_incremental is not None:
            self.refactron.config.enable_incremental_analysis = use_incremental

        start_time = time.time()
        result = self.refactron.analyze(target)
        self.session.analyze_ms = (time.time() - start_time) * 1000
        return result

    def queue_issues(self, issues: List[CodeIssue]) -> list:
        """Queue issues mapped to their responsible fixers."""
        start_time = time.time()
        queued = []
        for issue in issues:
            fixer_name = self._find_fixer_name(issue)
            if fixer_name:
                queued.append({"issue": issue, "fixer_name": fixer_name})
        self.session.queue_ms = (time.time() - start_time) * 1000
        return queued

    def _find_fixer_name(self, issue: CodeIssue) -> Optional[str]:
        """Find the appropriate fixer name for a given issue."""
        # Use rule_id or category as cache key
        issue_type = issue.rule_id or str(getattr(issue, "category", type(issue).__name__))
        if issue_type in self._fixer_cache:
            return self._fixer_cache[issue_type]

        candidate_name = None

        # 1. Ask AutoFixEngine directly without preview (O(1) dictionary lookup)
        if hasattr(self, "autofix_engine") and self.autofix_engine.can_fix(issue):
            candidate_name = issue.rule_id
        else:
            # 2. Fallback to preview-based resolution for ambiguous cases
            if hasattr(self, "autofix_engine"):
                for name, fixer in self.autofix_engine.fixers.items():
                    try:
                        preview_result = fixer.preview(issue, "x = 1\n")
                        if preview_result and getattr(preview_result, "success", False):
                            candidate_name = name
                            break
                    except Exception:
                        continue

        self._fixer_cache[issue_type] = candidate_name
        return candidate_name

    def apply(
        self, queued_issues: List[dict], preview: bool = False, fail_fast: bool = False
    ) -> list:
        """
        Apply fixes for queued issues.

        Orchestration Policies:
        - Best-effort (default): Continues applying fixes to other files even if one file fails.
        - Fail-fast (fail_fast=True): Stops the entire application process on the first file failure.

        Args:
            queued_issues: List of dicts containing 'issue' and 'fixer_name'.
            preview: If True, only simulate fixes (no disk writes).
            fail_fast: If True, stop on first application error.

        Returns:
            List of results for each application attempt.
        """
        start_time = time.time()
        results = []

        # 1. Group issues by file to ensure atomic/cumulative updates
        file_map = defaultdict(list)
        for item in queued_issues:
            file_map[item["issue"].file_path].append(item)

        self.session.files_attempted = len(file_map)

        # 2. Setup Backup
        backup_system = BackupRollbackSystem(self.project_root)
        session_id = None
        if not preview and self._config.backup_enabled and file_map:
            try:
                session_id, _ = backup_system.prepare_for_refactoring(
                    list(file_map.keys()), description=f"Pipeline session {self.session.id}"
                )
                self.session.backup_session_id = session_id
            except Exception as e:
                logger.warning(f"Failed to create backup session: {e}")

        # 3. Apply fixes file by file
        for file_path, items in file_map.items():
            success = True
            try:
                content = file_path.read_text(encoding="utf-8")
                current_code = content

                # Apply each fixer sequentially for this file
                for item in items:
                    issue = item["issue"]
                    fix_result = self.autofix_engine.fix(issue, current_code, preview=preview)
                    results.append(fix_result)

                    if fix_result.success:
                        current_code = fix_result.fixed_code
                    else:
                        success = False
                        self.session.blocked_fixes.append(
                            {
                                "file": str(file_path),
                                "issue": issue.message,
                                "reason": fix_result.reason,
                            }
                        )

                # Write back if successful and not in preview
                if not preview and success:
                    file_path.write_text(current_code, encoding="utf-8")
                    self.session.files_succeeded += 1
                elif not success:
                    self.session.files_failed += 1
                    if fail_fast:
                        break
                else:
                    # Preview mode success
                    self.session.files_succeeded += 1

            except Exception as e:
                self.session.files_failed += 1
                self.session.blocked_fixes.append({"file": str(file_path), "error": str(e)})
                results.append(None)
                if fail_fast:
                    break

        self.session.apply_ms = (time.time() - start_time) * 1000
        return results

    def verify(self, target: Union[str, Path]) -> AnalysisResult:
        """Verify the state of the project after fixes."""
        start_time = time.time()
        result = self.analyze(target)
        self.session.verify_ms = (time.time() - start_time) * 1000
        return result
