"""Pipeline orchestration for automated and session-based flows."""

from pathlib import Path
from typing import Optional, Union, List

from refactron.core.config import RefactronConfig
from refactron.core.refactron import Refactron
from refactron.core.analysis_result import AnalysisResult
from refactron.core.models import CodeIssue
from refactron.autofix.engine import AutoFixEngine

class RefactronPipeline:
    """Automated pipeline execution for session-based and CI/CD flows."""

    def __init__(self, project_root: Optional[Union[str, Path]] = None, config_path: Optional[Union[str, Path]] = None):
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

    def _load_config(self) -> RefactronConfig:
        if self.config_path and self.config_path.exists():
            return RefactronConfig.from_file(self.config_path)
            
        root = self.project_root or Path.cwd()
        yaml_path = root / ".refactron.yaml"
        if yaml_path.exists():
            return RefactronConfig.from_file(yaml_path)
        return RefactronConfig.default()

    def analyze(self, target: Union[str, Path], use_incremental: Optional[bool] = None) -> AnalysisResult:
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

        return self.refactron.analyze(target)

    def queue_issues(self, issues: List[CodeIssue]) -> list:
        """Queue issues mapped to their responsible fixers."""
        queued = []
        for issue in issues:
            fixer_name = self._find_fixer_name(issue)
            if fixer_name:
                queued.append({"issue": issue, "fixer_name": fixer_name})
        return queued
        
    def _find_fixer_name(self, issue: CodeIssue) -> Optional[str]:
        """Find the appropriate fixer name for a given issue."""
        # Use rule_id or category as cache key
        issue_type = issue.rule_id or str(getattr(issue, 'category', type(issue).__name__))
        if issue_type in self._fixer_cache:
            return self._fixer_cache[issue_type]

        candidate_name = None

        # 1. Ask AutoFixEngine directly without preview (O(1) dictionary lookup)
        if hasattr(self, 'autofix_engine') and self.autofix_engine.can_fix(issue):
            candidate_name = issue.rule_id
        else:
            # 2. Fallback to preview-based resolution for ambiguous cases
            if hasattr(self, 'autofix_engine'):
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
