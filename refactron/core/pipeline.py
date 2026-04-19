"""Pipeline orchestration for automated and session-based flows."""

from pathlib import Path
from typing import Optional, Union

from refactron.core.config import RefactronConfig
from refactron.core.refactron import Refactron
from refactron.core.analysis_result import AnalysisResult

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
