import json
import time
from pathlib import Path
from refactron.analysis.symbol_table import SymbolTableBuilder, SymbolType


def test_symbol_table_incremental_build(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()

    file1 = project_root / "module1.py"
    file1.write_text("def func1(): pass\nclass Class1: pass")

    cache_dir = tmp_path / "cache"
    builder = SymbolTableBuilder(cache_dir=cache_dir)

    # 1. First build
    table = builder.build_for_project(project_root)
    assert "func1" in table.exports
    assert "Class1" in table.exports

    cache_file = cache_dir / "symbols.json"
    assert cache_file.exists()

    with open(cache_file, "r") as f:
        cache_data = json.load(f)
    assert file1.resolve().as_posix() in cache_data["file_metadata"]

    # 2. Second build (no change)
    # We'll monkeypatch _analyze_file to verify it's not called
    original_analyze = builder._analyze_file
    analyze_called = []

    def mocked_analyze(path):
        analyze_called.append(path)
        return original_analyze(path)

    builder._analyze_file = mocked_analyze
    table2 = builder.build_for_project(project_root)

    assert len(analyze_called) == 0
    assert "func1" in table2.exports

    # 3. Modify file (incremental update)
    time.sleep(0.1)  # Ensure mtime changes
    file1.write_text("def func1_v2(): pass\nclass Class1: pass")

    analyze_called.clear()
    table3 = builder.build_for_project(project_root)

    assert len(analyze_called) == 1
    assert "func1_v2" in table3.exports
    assert "func1" not in table3.exports
    assert "Class1" in table3.exports

    # 4. Add new file
    file2 = project_root / "module2.py"
    file2.write_text("var2 = 42")

    analyze_called.clear()
    table4 = builder.build_for_project(project_root)

    assert len(analyze_called) == 1
    assert file2.resolve().as_posix() in [p.as_posix() for p in analyze_called]
    assert "var2" in table4.exports

    # 5. Delete file
    file1.unlink()

    analyze_called.clear()
    table5 = builder.build_for_project(project_root)

    assert len(analyze_called) == 0
    assert "func1_v2" not in table5.exports
    assert "Class1" not in table5.exports
    assert "var2" in table5.exports
    assert file1.resolve().as_posix() not in table5.file_metadata


def test_symbol_table_hash_validation(tmp_path):
    """Verify that content change triggers re-analysis even if mtime stays the same."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    file1 = project_root / "module1.py"
    file1.write_text("x = 1")

    cache_dir = tmp_path / "cache"
    builder = SymbolTableBuilder(cache_dir=cache_dir)

    # Initial build
    builder.build_for_project(project_root)
    original_mtime = file1.stat().st_mtime
    original_size = file1.stat().st_size

    # Modify content but keep same size and restore mtime (simulated)
    # Actually, hard to keep same size AND restore mtime exactly in some FS,
    # but we can try.
    file1.write_text("y = 2")  # same size "x = 1" vs "y = 2"
    import os

    os.utime(file1, (original_mtime, original_mtime))

    # Verify mtime/size match but content hash differs
    assert file1.stat().st_mtime == original_mtime
    assert file1.stat().st_size == original_size

    analyze_called = []
    original_analyze = builder._analyze_file

    def mocked_analyze(path):
        analyze_called.append(path)
        return original_analyze(path)

    builder._analyze_file = mocked_analyze

    table = builder.build_for_project(project_root)

    # Should detect change via hash
    assert len(analyze_called) == 1
    assert "y" in table.exports
    assert "x" not in table.exports
