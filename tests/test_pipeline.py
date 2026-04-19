"""Tests for the Refactron pipeline module."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from refactron.core.pipeline import RefactronPipeline
from refactron.core.config import RefactronConfig

def test_pipeline_loads_project_config():
    """Test that RefactronPipeline loads configuration from the project root."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root_path = Path(temp_dir)
        
        config_path = root_path / ".refactron.yaml"
        config_path.write_text("max_function_complexity: 99\nenable_metrics: false\n")
        
        target_file = root_path / "dummy.py"
        target_file.write_text("def foo():\n    pass\n")
        
        with patch("refactron.core.pipeline.Refactron.analyze") as mock_analyze:
            mock_analyze.return_value = "mock_result"
            pipeline = RefactronPipeline(project_root=root_path)
            
            result = pipeline.analyze(target_file)
            
            assert result == "mock_result"
            config_passed = pipeline.refactron.config
            
            assert isinstance(config_passed, RefactronConfig)
            assert config_passed.max_function_complexity == 99
            assert config_passed.enable_metrics is False
            assert config_passed.enable_incremental_analysis is False

def test_pipeline_incremental_override():
    """Test that RefactronPipeline can override the incremental setting."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root_path = Path(temp_dir)
        
        target_file = root_path / "dummy.py"
        target_file.write_text("def foo():\n    pass\n")
        
        with patch("refactron.core.pipeline.Refactron.analyze"):
            pipeline = RefactronPipeline(project_root=root_path)
            pipeline.analyze(target_file, use_incremental=True)
            
            config_passed = pipeline.refactron.config
            assert config_passed.enable_incremental_analysis is True
