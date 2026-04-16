"""Tests for enhanced configuration management features."""

from __future__ import annotations

import io
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import libcst as cst
import pytest
import yaml

from refactron.core import device_auth, repositories
from refactron.core.analysis_result import FileAnalysisError
from refactron.core.cache import ASTCache
from refactron.core.config import RefactronConfig
from refactron.core.config_loader import ConfigLoader
from refactron.core.config_templates import ConfigTemplates
from refactron.core.config_validator import ConfigValidator
from refactron.core.credentials import (
    RefactronCredentials,
    credentials_path,
    delete_credentials,
    load_credentials,
    save_credentials,
)
from refactron.core.device_auth import DeviceAuthorization
from refactron.core.exceptions import ConfigError
from refactron.core.incremental import IncrementalAnalysisTracker
from refactron.core.memory_profiler import (
    MemoryProfiler,
    MemorySnapshot,
    estimate_file_size_mb,
    stream_large_file,
)
from refactron.core.models import FileMetrics
from refactron.core.parallel import ParallelProcessor
from refactron.core.repositories import Repository, list_repositories
from refactron.core.workspace import WorkspaceManager, WorkspaceMapping


class TestConfigValidator:
    """Tests for configuration schema validation."""

    def test_validate_valid_config(self) -> None:
        """Test validation of valid configuration."""
        config = {
            "version": "1.0",
            "enabled_analyzers": ["complexity", "security"],
            "max_function_complexity": 10,
        }
        errors = ConfigValidator.validate(config)
        assert len(errors) == 0

    def test_validate_invalid_analyzer(self) -> None:
        """Test validation catches invalid analyzer names."""
        config = {
            "version": "1.0",
            "enabled_analyzers": ["invalid_analyzer"],
        }
        with pytest.raises(ConfigError) as exc_info:
            ConfigValidator.validate(config)
        assert "Invalid analyzer" in str(exc_info.value)

    def test_validate_invalid_version(self) -> None:
        """Test validation catches unsupported version."""
        config = {
            "version": "2.0",
            "enabled_analyzers": ["complexity"],
        }
        with pytest.raises(ConfigError) as exc_info:
            ConfigValidator.validate(config)
        assert "Unsupported config version" in str(exc_info.value)

    def test_validate_invalid_numeric_value(self) -> None:
        """Test validation catches invalid numeric values."""
        config = {
            "version": "1.0",
            "max_function_complexity": -5,  # Invalid: must be >= 1
        }
        with pytest.raises(ConfigError) as exc_info:
            ConfigValidator.validate(config)
        assert "max_function_complexity" in str(exc_info.value)

    def test_validate_invalid_environment(self) -> None:
        """Test validation catches invalid environment."""
        config = {
            "version": "1.0",
            "environment": "invalid_env",
        }
        with pytest.raises(ConfigError) as exc_info:
            ConfigValidator.validate(config)
        assert "Invalid environment" in str(exc_info.value)

    def test_validate_invalid_log_level(self) -> None:
        """Test validation catches invalid log level."""
        config = {
            "version": "1.0",
            "log_level": "INVALID",
        }
        with pytest.raises(ConfigError) as exc_info:
            ConfigValidator.validate(config)
        assert "Invalid log_level" in str(exc_info.value)


class TestConfigLoader:
    """Tests for configuration loading with profiles."""

    def test_load_base_config(self) -> None:
        """Test loading base configuration without profiles."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config = {
                "version": "1.0",
                "base": {
                    "enabled_analyzers": ["complexity"],
                    "log_level": "INFO",
                },
            }
            yaml.dump(config, f)
            config_path = Path(f.name)

        try:
            loaded = ConfigLoader.load_from_file(config_path)
            assert loaded["enabled_analyzers"] == ["complexity"]
            assert loaded["log_level"] == "INFO"
        finally:
            config_path.unlink()

    def test_load_with_profile(self) -> None:
        """Test loading configuration with profile override."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config = {
                "version": "1.0",
                "base": {
                    "enabled_analyzers": ["complexity"],
                    "log_level": "INFO",
                },
                "profiles": {
                    "dev": {
                        "log_level": "DEBUG",
                    },
                },
            }
            yaml.dump(config, f)
            config_path = Path(f.name)

        try:
            loaded = ConfigLoader.load_from_file(config_path, profile="dev")
            assert loaded["enabled_analyzers"] == ["complexity"]  # From base
            assert loaded["log_level"] == "DEBUG"  # From profile
            assert loaded["environment"] == "dev"
        finally:
            config_path.unlink()

    def test_load_with_environment_override(self) -> None:
        """Test environment overrides profile."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config = {
                "version": "1.0",
                "base": {
                    "log_level": "INFO",
                },
                "profiles": {
                    "dev": {"log_level": "DEBUG"},
                    "prod": {"log_level": "WARNING"},
                },
            }
            yaml.dump(config, f)
            config_path = Path(f.name)

        try:
            loaded = ConfigLoader.load_from_file(config_path, profile="dev", environment="prod")
            assert loaded["log_level"] == "WARNING"  # Environment takes precedence
            assert loaded["environment"] == "prod"
        finally:
            config_path.unlink()

    def test_load_legacy_config(self) -> None:
        """Test loading legacy config without base/profiles structure."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config = {
                "enabled_analyzers": ["complexity"],
                "log_level": "INFO",
            }
            yaml.dump(config, f)
            config_path = Path(f.name)

        try:
            loaded = ConfigLoader.load_from_file(config_path)
            assert loaded["enabled_analyzers"] == ["complexity"]
            assert loaded["log_level"] == "INFO"
        finally:
            config_path.unlink()

    def test_merge_nested_config(self) -> None:
        """Test deep merging of nested configuration."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config = {
                "version": "1.0",
                "base": {
                    "custom_rules": {
                        "rule1": "value1",
                        "rule2": "value2",
                    },
                },
                "profiles": {
                    "dev": {
                        "custom_rules": {
                            "rule2": "overridden",
                            "rule3": "value3",
                        },
                    },
                },
            }
            yaml.dump(config, f)
            config_path = Path(f.name)

        try:
            loaded = ConfigLoader.load_from_file(config_path, profile="dev")
            assert loaded["custom_rules"]["rule1"] == "value1"  # From base
            assert loaded["custom_rules"]["rule2"] == "overridden"  # From profile
            assert loaded["custom_rules"]["rule3"] == "value3"  # From profile
        finally:
            config_path.unlink()


class TestConfigTemplates:
    """Tests for configuration templates."""

    def test_get_base_template(self) -> None:
        """Test base template generation."""
        template = ConfigTemplates.get_base_template()
        assert "version" in template
        assert "base" in template
        assert "profiles" in template
        assert "dev" in template["profiles"]
        assert "staging" in template["profiles"]
        assert "prod" in template["profiles"]

    def test_get_django_template(self) -> None:
        """Test Django template generation."""
        template = ConfigTemplates.get_django_template()
        assert "migrations" in str(template["base"]["exclude_patterns"])
        assert "django_specific" in template["base"]["custom_rules"]

    def test_get_fastapi_template(self) -> None:
        """Test FastAPI template generation."""
        template = ConfigTemplates.get_fastapi_template()
        assert template["base"]["max_function_complexity"] == 15
        assert template["base"]["max_parameters"] == 10
        assert "fastapi_specific" in template["base"]["custom_rules"]

    def test_get_flask_template(self) -> None:
        """Test Flask template generation."""
        template = ConfigTemplates.get_flask_template()
        assert "flask_specific" in template["base"]["custom_rules"]

    def test_get_template_invalid_framework(self) -> None:
        """Test error handling for invalid framework."""
        with pytest.raises(ValueError) as exc_info:
            ConfigTemplates.get_template("invalid")
        assert "Unsupported framework" in str(exc_info.value)


class TestRefactronConfigEnhanced:
    """Tests for enhanced RefactronConfig with profiles."""

    def test_config_with_version(self) -> None:
        """Test config includes version field."""
        config = RefactronConfig()
        assert config.version == ConfigValidator.CURRENT_VERSION

    def test_config_with_environment(self) -> None:
        """Test config includes environment field."""
        config = RefactronConfig(environment="dev")
        assert config.environment == "dev"

    def test_from_file_with_profile(self) -> None:
        """Test loading config from file with profile."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config = {
                "version": "1.0",
                "base": {
                    "enabled_analyzers": ["complexity"],
                    "log_level": "INFO",
                },
                "profiles": {
                    "dev": {
                        "log_level": "DEBUG",
                    },
                },
            }
            yaml.dump(config, f)
            config_path = Path(f.name)

        try:
            loaded_config = RefactronConfig.from_file(config_path, profile="dev")
            assert loaded_config.log_level == "DEBUG"
            assert loaded_config.environment == "dev"
        finally:
            config_path.unlink()

    def test_from_file_with_environment(self) -> None:
        """Test loading config from file with environment."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config = {
                "version": "1.0",
                "base": {
                    "log_level": "INFO",
                },
                "profiles": {
                    "prod": {
                        "log_level": "WARNING",
                    },
                },
            }
            yaml.dump(config, f)
            config_path = Path(f.name)

        try:
            loaded_config = RefactronConfig.from_file(config_path, environment="prod")
            assert loaded_config.log_level == "WARNING"
            assert loaded_config.environment == "prod"
        finally:
            config_path.unlink()

    def test_from_file_legacy_format(self) -> None:
        """Test loading legacy config format (backward compatibility)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config = {
                "enabled_analyzers": ["complexity"],
                "log_level": "INFO",
            }
            yaml.dump(config, f)
            config_path = Path(f.name)

        try:
            loaded_config = RefactronConfig.from_file(config_path)
            assert loaded_config.enabled_analyzers == ["complexity"]
            assert loaded_config.log_level == "INFO"
            # Version should be set to current
            assert loaded_config.version == ConfigValidator.CURRENT_VERSION
        finally:
            config_path.unlink()

    def test_to_file_includes_version(self) -> None:
        """Test saving config includes version."""
        config = RefactronConfig()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_path = Path(f.name)

        try:
            config.to_file(config_path)
            with open(config_path) as f:
                saved = yaml.safe_load(f)
            assert saved["version"] == ConfigValidator.CURRENT_VERSION
        finally:
            config_path.unlink()


class TestConfigVersioning:
    """Tests for configuration versioning and backward compatibility."""

    def test_version_validation(self) -> None:
        """Test version validation."""
        ConfigValidator.validate_version_compatibility("1.0")
        with pytest.raises(ConfigError):
            ConfigValidator.validate_version_compatibility("2.0")

    def test_migrate_config_same_version(self) -> None:
        """Test migration when versions are the same."""
        config = {"version": "1.0", "log_level": "INFO"}
        migrated = ConfigLoader.migrate_config(config, "1.0", "1.0")
        assert migrated == config

    def test_migrate_config_unsupported_version(self) -> None:
        """Test migration from unsupported version."""
        config = {"version": "0.9", "log_level": "INFO"}
        with pytest.raises(ConfigError):
            ConfigLoader.migrate_config(config, "0.9", "1.0")


class TestConfigErrorMessages:
    """Tests for clear, actionable error messages."""

    def test_validation_error_with_suggestion(self) -> None:
        """Test validation errors include recovery suggestions."""
        config = {
            "version": "1.0",
            "enabled_analyzers": ["invalid"],
        }
        with pytest.raises(ConfigError) as exc_info:
            ConfigValidator.validate(config)
        error = exc_info.value
        assert error.recovery_suggestion is not None
        assert len(error.recovery_suggestion) > 0

    def test_load_error_with_suggestion(self) -> None:
        """Test load errors include recovery suggestions."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: syntax: [")
            config_path = Path(f.name)

        try:
            with pytest.raises(ConfigError) as exc_info:
                ConfigLoader.load_from_file(config_path)
            error = exc_info.value
            assert error.recovery_suggestion is not None
        finally:
            config_path.unlink()


# ─────────────── Core (boost) ───────────────


# ──────────────────────────── MemorySnapshot ──────────────────────────────────


class TestMemorySnapshot:
    def test_str(self):
        s = MemorySnapshot(rss_mb=100.0, vms_mb=200.0, percent=50.0, available_mb=1000.0)
        assert "RSS" in str(s) and "100.00" in str(s)


# ──────────────────────────── MemoryProfiler ──────────────────────────────────


class TestMemoryProfiler:
    def test_init_with_psutil(self):
        mock_psutil = MagicMock()
        mock_proc = MagicMock()
        mock_psutil.Process.return_value = mock_proc
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            mp = MemoryProfiler()
        assert mp._psutil_available

    def test_init_without_psutil(self):
        with patch.dict("sys.modules", {"psutil": None}):
            mp = MemoryProfiler()
        assert not mp._psutil_available

    def test_get_current_memory_fallback(self):
        mp = MemoryProfiler()
        mp._psutil_available = False
        snap = mp.get_current_memory()
        assert snap.rss_mb == 0.0

    def test_get_current_memory_with_psutil(self):
        mp = MemoryProfiler()
        mp._psutil_available = True
        mem_info = MagicMock()
        mem_info.rss = 100 * 1024 * 1024
        mem_info.vms = 200 * 1024 * 1024
        virtual_mem = MagicMock()
        virtual_mem.percent = 50.0
        virtual_mem.available = 1024 * 1024 * 1024
        mp._process = MagicMock()
        mp._process.memory_info.return_value = mem_info
        mp._psutil = MagicMock()
        mp._psutil.virtual_memory.return_value = virtual_mem
        snap = mp.get_current_memory()
        assert snap.rss_mb == pytest.approx(100.0)

    def test_get_current_memory_psutil_exception(self):
        mp = MemoryProfiler()
        mp._psutil_available = True
        mp._process = MagicMock()
        mp._process.memory_info.side_effect = Exception("read error")
        snap = mp.get_current_memory()
        assert snap.rss_mb == 0.0

    def test_snapshot_disabled(self):
        mp = MemoryProfiler(enabled=False)
        snap = mp.snapshot("label")
        assert snap.rss_mb == 0.0

    def test_snapshot_stores(self):
        mp = MemoryProfiler()
        mp.get_current_memory = MagicMock(return_value=MemorySnapshot(1.0, 2.0, 50.0, 100.0))
        mp.snapshot("test")
        assert "test" in mp._snapshots

    def test_compare_missing_label(self):
        mp = MemoryProfiler()
        result = mp.compare("a", "b")
        assert result == {}

    def test_compare_snapshots(self):
        mp = MemoryProfiler()
        mp._snapshots["start"] = MemorySnapshot(100.0, 200.0, 50.0, 500.0)
        mp._snapshots["end"] = MemorySnapshot(110.0, 210.0, 52.0, 490.0)
        diff = mp.compare("start", "end")
        assert diff["rss_mb_diff"] == pytest.approx(10.0)

    def test_profile_function_disabled(self):
        mp = MemoryProfiler(enabled=False)
        result, info = mp.profile_function(lambda: 42)
        assert result == 42 and info == {}

    def test_profile_function_enabled(self):
        mp = MemoryProfiler()
        mp.get_current_memory = MagicMock(return_value=MemorySnapshot(1.0, 2.0, 50.0, 100.0))
        result, diff = mp.profile_function(lambda: "hello")
        assert result == "hello"

    def test_optimize_for_large_file_above_threshold(self):
        mp = MemoryProfiler()
        assert mp.optimize_for_large_files(10.0) is True

    def test_optimize_for_large_file_below_threshold(self):
        mp = MemoryProfiler()
        assert mp.optimize_for_large_files(1.0) is False

    def test_optimize_for_large_file_custom_threshold(self):
        mp = MemoryProfiler()
        assert mp.optimize_for_large_files(3.0, threshold_mb=2.0) is True

    def test_check_memory_pressure_no_psutil(self):
        mp = MemoryProfiler()
        mp._psutil_available = False
        assert mp.check_memory_pressure() is False

    def test_check_memory_pressure_high(self):
        mp = MemoryProfiler(pressure_threshold_percent=60.0)
        mp._psutil_available = True
        mp.get_current_memory = MagicMock(return_value=MemorySnapshot(1.0, 2.0, 90.0, 1000.0))
        assert mp.check_memory_pressure() is True

    def test_check_memory_pressure_low_available_mb(self):
        mp = MemoryProfiler(pressure_threshold_available_mb=1000.0)
        mp._psutil_available = True
        mp.get_current_memory = MagicMock(return_value=MemorySnapshot(1.0, 2.0, 20.0, 100.0))
        assert mp.check_memory_pressure() is True

    def test_suggest_gc_disabled(self):
        mp = MemoryProfiler(enabled=False)
        mp.suggest_gc()  # No error

    def test_suggest_gc_enabled_no_pressure(self):
        mp = MemoryProfiler()
        mp._psutil_available = False
        mp.suggest_gc()  # No error

    def test_get_stats(self):
        mp = MemoryProfiler()
        mp.get_current_memory = MagicMock(return_value=MemorySnapshot(1.0, 2.0, 50.0, 100.0))
        stats = mp.get_stats()
        assert "enabled" in stats

    def test_clear_snapshots(self):
        mp = MemoryProfiler()
        mp._snapshots["x"] = MagicMock()
        mp.clear_snapshots()
        assert len(mp._snapshots) == 0


class TestStreamLargeFile:
    def test_streams_chunks(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_text("a" * 100)
        chunks = list(stream_large_file(str(f), chunk_size=10))
        assert "".join(chunks) == "a" * 100


class TestEstimateFileSizeMb:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "f.py"
        f.write_bytes(b"x" * 1024)
        mb = estimate_file_size_mb(str(f))
        assert mb > 0

    def test_missing_file(self):
        result = estimate_file_size_mb("/nonexistent/path.py")
        assert result == 0.0


# ──────────────────────────── ASTCache ────────────────────────────────────────


class TestASTCache:
    def test_disabled_get_returns_none(self, tmp_path):
        cache = ASTCache(cache_dir=tmp_path, enabled=False)
        assert cache.get(Path("a.py"), "x=1") is None

    def test_disabled_put_does_nothing(self, tmp_path):
        cache = ASTCache(cache_dir=tmp_path, enabled=False)
        cache.put(Path("a.py"), "x=1", MagicMock())  # No error

    def test_put_and_get_memory_hit(self, tmp_path):
        cache = ASTCache(cache_dir=tmp_path, enabled=True)
        mock_module = MagicMock()
        cache.put(Path("a.py"), "x=1", mock_module, metadata={"key": "val"})
        result = cache.get(Path("a.py"), "x=1")
        assert result is not None
        assert cache.stats["memory_hits"] == 1

    def test_disk_hit(self, tmp_path):

        cache = ASTCache(cache_dir=tmp_path, enabled=True)
        # Use a real cst.Module so pickle round-trip works
        real_module = cst.parse_module("x = 1\n")
        cache.put(Path("a.py"), "x=1", real_module)
        # Clear memory cache to force disk hit
        cache._memory_cache.clear()
        result = cache.get(Path("a.py"), "x=1")
        assert result is not None
        assert cache.stats["disk_hits"] == 1

    def test_cache_miss(self, tmp_path):
        cache = ASTCache(cache_dir=tmp_path, enabled=True)
        result = cache.get(Path("a.py"), "missing content")
        assert result is None
        assert cache.stats["misses"] == 1

    def test_corrupted_disk_cache_removed(self, tmp_path):
        cache = ASTCache(cache_dir=tmp_path, enabled=True)
        content_hash = cache._compute_hash("x=1")
        cache_path = cache._get_cache_path(content_hash)
        cache_path.write_bytes(b"not valid pickle")
        result = cache.get(Path("a.py"), "x=1")
        assert result is None
        assert not cache_path.exists()

    def test_clear(self, tmp_path):
        cache = ASTCache(cache_dir=tmp_path, enabled=True)
        cache.put(Path("a.py"), "x=1", MagicMock())
        cache.clear()
        assert len(cache._memory_cache) == 0
        assert cache.stats["hits"] == 0

    def test_get_stats(self, tmp_path):
        cache = ASTCache(cache_dir=tmp_path, enabled=True)
        cache.put(Path("a.py"), "x=1", MagicMock())
        cache.get(Path("a.py"), "x=1")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["hit_rate_percent"] == 100.0

    def test_cleanup_when_size_exceeds_limit(self, tmp_path):
        cache = ASTCache(cache_dir=tmp_path, enabled=True, max_cache_size_mb=1)
        # Add many fake cache files
        for i in range(5):
            cf = cache.cache_dir / f"fake{i}.cache"
            cf.write_bytes(b"x" * (300 * 1024))  # 300KB each = 1.5MB total
        cache._cleanup_if_needed()  # Should remove some files

    def test_put_write_error_handled(self, tmp_path):
        cache = ASTCache(cache_dir=tmp_path, enabled=True)
        with patch("builtins.open", side_effect=OSError("disk full")):
            cache.put(Path("a.py"), "x=1", MagicMock())  # Should not raise

    def test_init_with_none_cache_dir(self):
        cache = ASTCache(cache_dir=None, enabled=True)
        assert "refactron_ast_cache" in str(cache.cache_dir)


# ──────────────────────────── core/repositories.py ────────────────────────────


class TestRepositoryFromDict:
    def test_from_dict_full(self):
        from refactron.core.repositories import Repository

        data = {
            "id": 1,
            "name": "repo",
            "full_name": "user/repo",
            "description": "desc",
            "private": False,
            "html_url": "https://github.com/user/repo",
            "clone_url": "https://github.com/user/repo.git",
            "ssh_url": "git@github.com:user/repo.git",
            "default_branch": "main",
            "language": "Python",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        repo = Repository.from_dict(data)
        assert repo.name == "repo"

    def test_from_dict_optional_fields(self):

        data = {
            "id": 2,
            "name": "r",
            "full_name": "u/r",
            "private": True,
            "html_url": "https://github.com/u/r",
            "clone_url": "https://github.com/u/r.git",
            "ssh_url": "git@github.com:u/r.git",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        repo = Repository.from_dict(data)
        assert repo.description is None
        assert repo.default_branch == "main"


class TestListRepositories:
    def test_not_authenticated(self):
        from refactron.core.repositories import list_repositories

        with patch("refactron.core.repositories.load_credentials", return_value=None):
            with pytest.raises(RuntimeError, match="Not authenticated"):
                list_repositories("https://api.test")

    def test_no_access_token(self):

        creds = MagicMock()
        creds.access_token = None
        with patch("refactron.core.repositories.load_credentials", return_value=creds):
            with pytest.raises(RuntimeError, match="No access token"):
                list_repositories("https://api.test")

    def test_expired_token(self):

        creds = MagicMock()
        creds.access_token = "token"
        creds.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        with patch("refactron.core.repositories.load_credentials", return_value=creds):
            with pytest.raises(RuntimeError, match="expired"):
                list_repositories("https://api.test")

    def test_success_list_response(self):

        creds = MagicMock()
        creds.access_token = "token"
        creds.expires_at = None

        repo_data = [
            {
                "id": 1,
                "name": "r",
                "full_name": "u/r",
                "private": False,
                "html_url": "h",
                "clone_url": "c",
                "ssh_url": "s",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        ]
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(repo_data).encode()

        with patch("refactron.core.repositories.load_credentials", return_value=creds), patch(
            "refactron.core.repositories.urlopen", return_value=mock_resp
        ):
            repos = list_repositories("https://api.test")
        assert len(repos) == 1

    def test_dict_wrapper_response(self):

        creds = MagicMock()
        creds.access_token = "token"
        creds.expires_at = None

        repo_data = {
            "repositories": [
                {
                    "id": 1,
                    "name": "r",
                    "full_name": "u/r",
                    "private": False,
                    "html_url": "h",
                    "clone_url": "c",
                    "ssh_url": "s",
                    "updated_at": "2024-01-01T00:00:00Z",
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(repo_data).encode()

        with patch("refactron.core.repositories.load_credentials", return_value=creds), patch(
            "refactron.core.repositories.urlopen", return_value=mock_resp
        ):
            repos = list_repositories("https://api.test")
        assert len(repos) == 1

    def test_http_401_raises(self):
        from urllib.error import HTTPError

        creds = MagicMock()
        creds.access_token = "token"
        creds.expires_at = None

        err = HTTPError("url", 401, "Unauthorized", {}, None)
        err.read = lambda: b'{"message": "bad token"}'

        with patch("refactron.core.repositories.load_credentials", return_value=creds), patch(
            "refactron.core.repositories.urlopen", side_effect=err
        ):
            with pytest.raises(RuntimeError, match="401"):
                list_repositories("https://api.test")

    def test_http_403_raises(self):

        creds = MagicMock()
        creds.access_token = "token"
        creds.expires_at = None

        err = HTTPError("url", 403, "Forbidden", {}, None)

        with patch("refactron.core.repositories.load_credentials", return_value=creds), patch(
            "refactron.core.repositories.urlopen", side_effect=err
        ):
            with pytest.raises(RuntimeError, match="GitHub access denied"):
                list_repositories("https://api.test")

    def test_url_error_raises(self):
        from urllib.error import URLError

        creds = MagicMock()
        creds.access_token = "token"
        creds.expires_at = None

        with patch("refactron.core.repositories.load_credentials", return_value=creds), patch(
            "refactron.core.repositories.urlopen", side_effect=URLError("network down")
        ):
            with pytest.raises(RuntimeError, match="Network error"):
                list_repositories("https://api.test")

    def test_invalid_json_raises(self):

        creds = MagicMock()
        creds.access_token = "token"
        creds.expires_at = None

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b"not json"

        with patch("refactron.core.repositories.load_credentials", return_value=creds), patch(
            "refactron.core.repositories.urlopen", return_value=mock_resp
        ):
            with pytest.raises(RuntimeError, match="Invalid JSON"):
                list_repositories("https://api.test")


# ─────────────── Core Infra (boost) ───────────────


def test_credentials_roundtrip_and_bad_inputs(tmp_path: Path) -> None:
    cred_path = tmp_path / "credentials.json"
    creds = RefactronCredentials(
        api_base_url="https://api.example.test",
        access_token="tok",
        token_type="Bearer",
    )
    save_credentials(creds, cred_path)
    loaded = load_credentials(cred_path)
    assert loaded is not None
    assert loaded.api_base_url == "https://api.example.test"
    assert delete_credentials(cred_path) is True
    assert delete_credentials(cred_path) is False

    cred_path.write_text("not-json", encoding="utf-8")
    assert load_credentials(cred_path) is None
    cred_path.write_text(json.dumps(["bad"]), encoding="utf-8")
    assert load_credentials(cred_path) is None
    cred_path.write_text(json.dumps({"api_base_url": "", "access_token": "x"}), encoding="utf-8")
    assert load_credentials(cred_path) is None
    assert isinstance(credentials_path(), Path)


def test_ast_cache_get_put_corrupt_and_clear(tmp_path: Path) -> None:
    cache = ASTCache(cache_dir=tmp_path / "cache")
    path = tmp_path / "a.py"
    content = "x = 1\n"
    module = cst.parse_module(content)

    assert cache.get(path, content) is None
    cache.put(path, content, module, metadata={"k": 1})
    got = cache.get(path, content)
    assert got is not None
    assert got[1]["k"] == 1

    # Corrupt cache file should be handled and removed.
    bad_hash = cache._compute_hash("broken")
    bad_file = cache._get_cache_path(bad_hash)
    bad_file.write_bytes(b"\x80not-a-pickle")
    assert cache.get(path, "broken") is None
    assert not bad_file.exists()

    stats = cache.get_stats()
    assert stats["enabled"] is True
    cache.clear()
    assert cache.get_stats()["cache_file_count"] == 0


def test_parallel_processor_sequential_and_thread_modes(tmp_path: Path) -> None:
    files = [tmp_path / "ok.py", tmp_path / "bad.py"]
    for f in files:
        f.write_text("x=1\n", encoding="utf-8")

    def process_func(p: Path):
        if p.name == "bad.py":
            raise ValueError("boom")
        return None, None, None

    p_seq = ParallelProcessor(max_workers=1, use_processes=False, enabled=True)
    _, errors, skips = p_seq.process_files(files, process_func)
    assert p_seq.enabled is False
    assert len(errors) == 1
    assert isinstance(errors[0], FileAnalysisError)

    p_thr = ParallelProcessor(max_workers=2, use_processes=False, enabled=True)
    results, errors, skips = p_thr.process_files(files, lambda p: (None, None, None))
    assert results == []
    assert errors == []
    assert p_thr.get_config()["max_workers"] == 2


def test_incremental_tracker_changed_files_and_cleanup(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    tracker = IncrementalAnalysisTracker(state_file=state_file, enabled=True)
    file1 = tmp_path / "f1.py"
    file2 = tmp_path / "f2.py"
    file1.write_text("x=1\n", encoding="utf-8")
    file2.write_text("y=2\n", encoding="utf-8")

    assert tracker.has_file_changed(file1) is True
    tracker.update_file_state(file1)
    assert tracker.has_file_changed(file1) is False
    changed = tracker.get_changed_files([file1, file2])
    assert file2 in changed
    tracker.update_file_state(file2)
    tracker.save()
    assert state_file.exists()

    tracker.remove_file_state(file2)
    tracker.cleanup_missing_files({file1})
    stats = tracker.get_stats()
    assert stats["tracked_files"] >= 1

    tracker.clear()
    assert tracker.get_stats()["tracked_files"] == 0


# ─────────────── Core Low Coverage (boost) ───────────────


class _FakeHttpResponse:
    def __init__(self, payload: str):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _valid_creds(expires_at=None) -> RefactronCredentials:
    return RefactronCredentials(
        api_base_url="https://api.refactron.dev",
        access_token="token",
        token_type="Bearer",
        expires_at=expires_at,
        email="a@b.com",
        plan="pro",
    )


def test_workspace_add_get_list_remove(tmp_path: Path) -> None:
    mgr = WorkspaceManager(config_path=tmp_path / "workspaces.json")
    mapping = WorkspaceMapping(
        repo_name="demo",
        repo_full_name="user/demo",
        local_path=str(tmp_path / "demo"),
        connected_at="2026-03-24T00:00:00Z",
        repo_id=42,
    )

    mgr.add_workspace(mapping)
    assert mgr.get_workspace("user/demo").repo_name == "demo"
    assert mgr.get_workspace("demo").repo_full_name == "user/demo"
    assert mgr.get_workspace_by_path(str(tmp_path / "demo")).repo_full_name == "user/demo"
    assert len(mgr.list_workspaces()) == 1
    assert mgr.remove_workspace("user/demo") is True
    assert mgr.remove_workspace("user/demo") is False


def test_workspace_load_invalid_json_returns_empty(tmp_path: Path) -> None:
    cfg = tmp_path / "workspaces.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("{broken", encoding="utf-8")
    mgr = WorkspaceManager(config_path=cfg)
    assert mgr.list_workspaces() == []


def test_workspace_detect_repository_https_ssh_and_missing(tmp_path: Path) -> None:
    mgr = WorkspaceManager(config_path=tmp_path / "workspaces.json")

    https_repo = tmp_path / "repo_https"
    (https_repo / ".git").mkdir(parents=True)
    (https_repo / ".git" / "config").write_text(
        '[remote "origin"]\nurl = https://github.com/acme/project.git\n',
        encoding="utf-8",
    )
    assert mgr.detect_repository(https_repo) == "acme/project"

    ssh_repo = tmp_path / "repo_ssh"
    (ssh_repo / ".git").mkdir(parents=True)
    (ssh_repo / ".git" / "config").write_text(
        '[remote "origin"]\nurl = git@github.com:acme/project2.git\n',
        encoding="utf-8",
    )
    assert mgr.detect_repository(ssh_repo) == "acme/project2"

    missing = tmp_path / "no_repo"
    missing.mkdir()
    assert mgr.detect_repository(missing) is None


def test_list_repositories_success_for_list_and_dict(monkeypatch) -> None:
    monkeypatch.setattr(repositories, "load_credentials", lambda: _valid_creds())

    payloads = [
        json.dumps(
            [
                {
                    "id": 1,
                    "name": "repo",
                    "full_name": "u/repo",
                    "description": None,
                    "private": False,
                    "html_url": "https://github.com/u/repo",
                    "clone_url": "https://github.com/u/repo.git",
                    "ssh_url": "git@github.com:u/repo.git",
                    "default_branch": "main",
                    "language": "Python",
                    "updated_at": "2026-03-24T00:00:00Z",
                }
            ]
        ),
        json.dumps({"repositories": []}),
    ]

    def fake_urlopen(req, timeout=10):  # noqa: ARG001
        return _FakeHttpResponse(payloads.pop(0))

    monkeypatch.setattr(repositories, "urlopen", fake_urlopen)
    repos = repositories.list_repositories("https://api.refactron.dev/")
    assert len(repos) == 1
    assert repos[0].full_name == "u/repo"
    repos2 = repositories.list_repositories("https://api.refactron.dev/")
    assert repos2 == []


def test_list_repositories_auth_and_error_paths(monkeypatch) -> None:
    monkeypatch.setattr(repositories, "load_credentials", lambda: None)
    with pytest.raises(RuntimeError, match="Not authenticated"):
        repositories.list_repositories("https://api.refactron.dev")

    monkeypatch.setattr(
        repositories,
        "load_credentials",
        lambda: _valid_creds(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)),
    )
    with pytest.raises(RuntimeError, match="session has expired"):
        repositories.list_repositories("https://api.refactron.dev")

    monkeypatch.setattr(repositories, "load_credentials", lambda: _valid_creds())

    err = HTTPError(
        url="https://api.refactron.dev/api/github/repositories",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=io.BytesIO(b'{"message":"bad token"}'),
    )

    def raise_401(req, timeout=10):  # noqa: ARG001
        raise err

    monkeypatch.setattr(repositories, "urlopen", raise_401)
    with pytest.raises(RuntimeError, match="Authentication failed"):
        repositories.list_repositories("https://api.refactron.dev")

    def raise_network(req, timeout=10):  # noqa: ARG001
        raise URLError("down")

    monkeypatch.setattr(repositories, "urlopen", raise_network)
    with pytest.raises(RuntimeError, match="Network error"):
        repositories.list_repositories("https://api.refactron.dev")


def test_device_auth_helpers_and_start_authorization(monkeypatch) -> None:
    assert (
        device_auth._normalize_base_url("https://api.refactron.dev/") == "https://api.refactron.dev"
    )

    monkeypatch.setattr(
        device_auth,
        "_post_json",
        lambda *a, **k: {
            "device_code": "dc",
            "user_code": "uc",
            "verification_uri": "https://example.com",
            "expires_in": "900",
            "interval": "0",
        },
    )
    auth = device_auth.start_device_authorization()
    assert isinstance(auth, DeviceAuthorization)
    assert auth.interval == 1

    monkeypatch.setattr(device_auth, "_post_json", lambda *a, **k: {"device_code": "x"})
    with pytest.raises(RuntimeError, match="Invalid /oauth/device response"):
        device_auth.start_device_authorization()


def test_poll_for_token_pending_slowdown_success_and_expired(monkeypatch) -> None:
    calls = []
    responses = [
        {"error": "authorization_pending"},
        {"error": "slow_down"},
        {
            "access_token": "tok",
            "token_type": "Bearer",
            "expires_in": 1200,
            "user": {"email": "x@y.com"},
        },
    ]

    def fake_post(*a, **k):  # noqa: ARG001
        return responses.pop(0)

    def fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr(device_auth, "_post_json", fake_post)
    token = device_auth.poll_for_token(
        device_code="dc",
        interval_seconds=1,
        expires_in_seconds=30,
        sleep_fn=fake_sleep,
    )
    assert token.access_token == "tok"
    assert calls == [1, 6]

    monkeypatch.setattr(device_auth, "_post_json", lambda *a, **k: {"error": "expired_token"})
    with pytest.raises(RuntimeError, match="Device code expired"):
        device_auth.poll_for_token("dc", expires_in_seconds=5, sleep_fn=lambda *_: None)


# ─────────────── Core Parallel (boost) ───────────────


def make_metrics(path):
    m = MagicMock(spec=FileMetrics)
    m.file_path = path
    return m


def make_error(path):
    return FileAnalysisError(
        file_path=path, error_message="fail", error_type="Error", recovery_suggestion="check file"
    )


def success_func(p):
    return make_metrics(p), None, None


def error_func(p):
    return None, make_error(p), None


def raises_func(p):
    raise RuntimeError("unexpected")


class TestParallelProcessorInit:
    def test_default_workers_capped_at_8(self):
        with patch("multiprocessing.cpu_count", return_value=16):
            pp = ParallelProcessor()
        assert pp.max_workers <= 8

    def test_explicit_workers(self):
        pp = ParallelProcessor(max_workers=4)
        assert pp.max_workers == 4

    def test_max_workers_zero_forced_to_1(self):
        pp = ParallelProcessor(max_workers=0)
        assert pp.max_workers == 1

    def test_single_worker_disables_parallel(self):
        pp = ParallelProcessor(max_workers=1)
        assert pp.enabled is False

    def test_get_config(self):
        pp = ParallelProcessor(max_workers=2, use_processes=False, enabled=True)
        cfg = pp.get_config()
        assert cfg["max_workers"] == 2
        assert cfg["use_processes"] is False


class TestSequentialProcessing:
    def test_empty_files(self):
        pp = ParallelProcessor(enabled=False)
        results, errors, skips = pp.process_files([], success_func)
        assert results == [] and errors == [] and skips == []

    def test_single_file_success(self):
        pp = ParallelProcessor(enabled=False)
        files = [Path("a.py")]
        results, errors, skips = pp.process_files(files, success_func)
        assert len(results) == 1 and len(errors) == 0 and len(skips) == 0

    def test_single_file_error(self):
        pp = ParallelProcessor(enabled=False)
        results, errors, skips = pp.process_files([Path("a.py")], error_func)
        assert len(results) == 0 and len(errors) == 1 and len(skips) == 0

    def test_single_file_exception(self):
        pp = ParallelProcessor(enabled=False)
        results, errors, skips = pp.process_files([Path("a.py")], raises_func)
        assert len(errors) == 1

    def test_progress_callback(self):
        pp = ParallelProcessor(enabled=False)
        calls = []
        pp.process_files(
            [Path("a.py"), Path("b.py")],
            success_func,
            progress_callback=lambda c, t: calls.append((c, t)),
        )
        assert calls == [(1, 2), (2, 2)]


class TestThreadedProcessing:
    def test_two_files_threads(self):
        pp = ParallelProcessor(max_workers=2, use_processes=False, enabled=True)
        files = [Path("a.py"), Path("b.py")]
        results, errors, skips = pp.process_files(files, success_func)
        assert len(results) == 2
        assert len(skips) == 0

    def test_thread_error_handling(self):
        pp = ParallelProcessor(max_workers=2, use_processes=False, enabled=True)
        results, errors, skips = pp.process_files([Path("a.py"), Path("b.py")], raises_func)
        assert len(errors) == 2

    def test_thread_progress_callback(self):
        pp = ParallelProcessor(max_workers=2, use_processes=False, enabled=True)
        calls = []
        pp.process_files(
            [Path("a.py"), Path("b.py")],
            success_func,
            progress_callback=lambda c, t: calls.append(c),
        )
        assert len(calls) == 2

    def test_single_file_goes_sequential(self):
        pp = ParallelProcessor(max_workers=4, use_processes=False, enabled=True)
        results, errors, skips = pp.process_files([Path("a.py")], success_func)
        assert len(results) == 1


class TestProcessPoolProcessing:
    def test_process_pool_falls_back_on_exception(self):
        pp = ParallelProcessor(max_workers=2, use_processes=True, enabled=True)
        with patch(
            "refactron.core.parallel.ProcessPoolExecutor", side_effect=Exception("spawn fail")
        ):
            results, errors, skips = pp.process_files([Path("a.py")], success_func)
        assert len(results) == 1

    def test_process_pool_success(self):
        pp = ParallelProcessor(max_workers=2, use_processes=True, enabled=True)
        mock_future = MagicMock()
        mock_future.result.return_value = (make_metrics(Path("a.py")), None, None)
        mock_exec = MagicMock()
        mock_exec.__enter__ = lambda s: s
        mock_exec.__exit__ = MagicMock(return_value=False)
        mock_exec.submit = lambda f, p: mock_future
        with patch("refactron.core.parallel.ProcessPoolExecutor", return_value=mock_exec), patch(
            "refactron.core.parallel.as_completed", return_value=[mock_future]
        ):
            pp._process_parallel_processes([Path("a.py")], success_func)
