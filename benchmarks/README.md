# Benchmarks

This directory contains performance benchmarking scripts for Refactron.

## Running Benchmarks

```bash
# Run performance benchmark
python benchmarks/performance_benchmark.py
```

## Benchmark Scripts

### performance_benchmark.py

Measures the performance of core Refactron operations:
- Analysis time for different file sizes (small, medium, large)
- Refactoring suggestion generation time
- Caching effectiveness
- Parallel processing speedup
- Memory usage profiling
- Statistical analysis (mean, median, std dev, min, max)

Results are automatically saved to `benchmark_history.json` for tracking over time.

### Example Output

```
🚀 Starting Refactron Performance Benchmarks...

Benchmarking with small file...
Benchmarking with medium file...
Benchmarking with large file...
Benchmarking parallel processing...

================================================================================
REFACTRON PERFORMANCE BENCHMARK RESULTS
================================================================================

Operation: analyze_small
  Mean time:   0.0071s
  Median time: 0.0003s
  Min time:    0.0003s
  Max time:    0.0342s
  Std dev:     0.0152s
  Iterations:  5

Operation: analyze_with_cache_medium
  Mean time:   0.0003s
  Median time: 0.0003s
  Min time:    0.0002s
  Max time:    0.0004s
  Std dev:     0.0001s
  Iterations:  5

Operation: parallel_processing
  Sequential time: 0.0005s
  Parallel time:   0.0005s
  Speedup:         1.08x

Operation: memory_usage_large
  Memory delta (RSS): 0.00 MB
  Memory delta (VMS): 0.00 MB

================================================================================
PERFORMANCE OPTIMIZATION STATISTICS
================================================================================

AST Cache:
  enabled: True
  hits: 15
  misses: 5
  hit_rate_percent: 75.0
...
```

## Performance Optimization Features

### 1. AST Caching
- **Purpose**: Avoid re-parsing identical files
- **Configuration**: `enable_ast_cache`, `max_ast_cache_size_mb`
- **Benefits**: Up to 10x faster on repeated analysis
- **Location**: Cache stored in temp directory or custom path

### 2. Incremental Analysis
- **Purpose**: Only analyze changed files since last run
- **Configuration**: `enable_incremental_analysis`
- **Benefits**: Significantly faster on large codebases
- **State**: Tracked in `refactron_incremental_state.json`

### 3. Parallel Processing
- **Purpose**: Analyze multiple files concurrently
- **Configuration**: `enable_parallel_processing`, `max_parallel_workers`
- **Benefits**: Near-linear speedup on multi-core systems
- **Modes**: Multiprocessing or threading

### 4. Memory Profiling
- **Purpose**: Track and optimize memory usage for large codebases
- **Configuration**: `enable_memory_profiling`
- **Features**: Memory snapshots, pressure detection, optimization suggestions
- **Threshold**: Automatic optimization for files > 5MB

## Configuration Example

```python
from refactron.core.config import RefactronConfig

config = RefactronConfig(
    # Enable all performance optimizations
    enable_ast_cache=True,
    max_ast_cache_size_mb=100,
    enable_incremental_analysis=True,
    enable_parallel_processing=True,
    max_parallel_workers=4,
    enable_memory_profiling=True,
)
```

Or via YAML config file:

```yaml
enable_ast_cache: true
max_ast_cache_size_mb: 100
enable_incremental_analysis: true
enable_parallel_processing: true
max_parallel_workers: 4
enable_memory_profiling: true
```

## Adding New Benchmarks

To add a new benchmark:

1. Create a new function following the pattern:
```python
def benchmark_operation(name: str, operation, iterations: int = 5):
    # Benchmark logic
    pass
```

2. Add it to the main() function
3. Document it in this README

## Performance Goals

Current performance targets:
- Small file (100 lines): < 0.2s
- Medium file (500 lines): < 1.0s
- Large file (2000 lines): < 5.0s
- 100k+ LOC codebase: < 60s (with all optimizations)

### Optimization Impact
- **AST Cache**: 5-10x speedup on repeated analysis
- **Incremental Analysis**: Up to 90% reduction in analysis time
- **Parallel Processing**: 2-4x speedup on multi-core systems
- **Memory Optimization**: Handles codebases up to 1M+ LOC

## Continuous Monitoring

We track performance over time to:
- Identify performance regressions
- Validate optimization efforts
- Set realistic expectations for users
- Compare releases

Benchmark history is stored in `benchmark_history.json` (git-ignored).

## Memory Usage Guidelines

For large codebases (100k+ lines):
1. Enable all performance optimizations
2. Monitor memory with `enable_memory_profiling=True`
3. Adjust `max_ast_cache_size_mb` based on available memory
4. Use `max_parallel_workers` to balance speed vs memory
5. Clear caches periodically: `refactron.clear_caches()`

## Troubleshooting

**Cache not working?**
- Check cache directory permissions
- Verify `enable_ast_cache=True`
- Check cache stats: `refactron.get_performance_stats()`

**Incremental analysis always re-analyzing?**
- Verify state file location
- Check file modification times
- Clear state: `refactron.incremental_tracker.clear()`

**Parallel processing slower?**
- Small codebases may not benefit
- Try adjusting `max_parallel_workers`
- Check CPU utilization
- Consider overhead for process spawning

**High memory usage?**
- Reduce `max_ast_cache_size_mb`
- Lower `max_parallel_workers`
- Enable memory profiling to identify bottlenecks
- Clear caches regularly
