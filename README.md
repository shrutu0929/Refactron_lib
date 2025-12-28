# 🤖 Refactron

**The Intelligent Code Refactoring Transformer**

Refactron is a powerful Python library designed to eliminate technical debt, modernize legacy code, and automate code refactoring with intelligence and safety.

[![CI](https://github.com/Refactron-ai/Refactron_lib/workflows/CI/badge.svg)](https://github.com/Refactron-ai/Refactron_lib/actions)
[![PyPI version](https://badge.fury.io/py/refactron.svg)](https://pypi.org/project/refactron/)
[![Python Version](https://img.shields.io/pypi/pyversions/refactron.svg)](https://pypi.org/project/refactron/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-135%20passed-brightgreen)]()
[![Coverage](https://img.shields.io/badge/coverage-84%25-brightgreen)]()

## ✨ Features

### 🔍 Comprehensive Analysis

- **Security Scanning** - Detect eval(), exec(), SQL injection, shell injection, hardcoded secrets, SSRF vulnerabilities, cryptographic weaknesses
- **Code Smells** - Find magic numbers, long functions, too many parameters, deep nesting, repeated code blocks
- **Complexity Metrics** - Cyclomatic complexity, maintainability index, nested loop depth, method call chain complexity
- **Type Hints** - Identify missing or incomplete type annotations
- **Dead Code** - Detect unused functions, variables, and unreachable code
- **Dependencies** - Find circular imports, wildcard imports, deprecated modules
- **Performance Issues** - N+1 queries, inefficient list comprehensions, unnecessary iterations, inefficient string concatenation

### 🔧 Intelligent Refactoring

- **Extract Constants** - Replace magic numbers with named constants
- **Reduce Parameters** - Convert parameter lists into configuration objects
- **Simplify Conditionals** - Transform nested if statements into guard clauses
- **Add Docstrings** - Generate contextual documentation automatically
- **Extract Methods** - Suggest method extraction for complex functions
- **Before/After Previews** - See exactly what will change
- **Risk Scoring** - Know how safe each refactoring is (0.0 = perfectly safe, 1.0 = high risk)

### ⚡ Auto-Fix Capabilities

- **14 Automatic Fixers** - Remove unused imports, sort imports, fix formatting, extract magic numbers, add docstrings, and more
- **Safety Levels** - Control fix risk (safe/low/moderate/high)
- **Automatic Backups** - All changes backed up before applying
- **Rollback System** - Undo individual files or all at once

### 📊 Rich Reporting

- Multiple formats: Text, JSON, HTML
- Detailed issue categorization
- Technical debt quantification
- Confidence scores for security findings
- Context-aware analysis (reduces false positives)
- Export for CI/CD integration

## 🚀 Quick Start

### Installation

```bash
pip install refactron
```

### Basic Usage

```python
from refactron import Refactron

# Initialize Refactron
refactron = Refactron()

# Analyze your code
analysis = refactron.analyze("path/to/your/code.py")
print(analysis.report())

# Apply refactoring
result = refactron.refactor("path/to/your/code.py", preview=True)
result.show_diff()
result.apply()
```

### CLI Usage

```bash
# Initialize configuration
refactron init

# Analyze a file or directory
refactron analyze myproject/ --detailed

# Generate a report
refactron report myproject/ --format json -o report.json

# Preview refactoring suggestions
refactron refactor myfile.py --preview

# Auto-fix code issues
refactron autofix myfile.py --preview
refactron autofix myfile.py --apply

# Filter specific refactoring types
refactron refactor myfile.py --preview -t extract_constant -t add_docstring
```

### Example Output:

```
🔍 Refactron Analysis

     Analysis Summary     
┏━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric         ┃ Value ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Files Analyzed │     3 │
│ Total Issues   │    50 │
│ 🔴 Critical    │     3 │
│ ❌ Errors      │     0 │
│ ⚡ Warnings    │     8 │
│ ℹ️  Info        │    39 │
└────────────────┴───────┘

⚠️  Found 3 critical issue(s) that need immediate attention!
```

## 🎯 What Makes Refactron Different?

Unlike traditional linters and formatters, Refactron:

- **Holistic Approach** - Combines analysis, refactoring, and optimization in one tool
- **Context-Aware** - Understands code semantics, not just syntax. Reduces false positives with context-aware security analysis
- **Safe by Default** - Preview changes, risk scoring, automatic backups, and rollback support
- **Intelligent** - Confidence scores, false positive tracking, and contextual improvements
- **Business-Focused** - Quantify technical debt in actionable metrics
- **Production-Ready** - Stable release with comprehensive test coverage and real-world validation

## 💡 Real-World Examples

We've included practical examples in the `examples/` directory:

- `flask_api_example.py` - Common Flask API issues (security, code smells)
- `data_science_example.py` - Data science workflow improvements
- `cli_tool_example.py` - CLI application best practices

Try them out:

```bash
# Analyze the Flask example
refactron analyze examples/flask_api_example.py --detailed

# Get refactoring suggestions
refactron refactor examples/flask_api_example.py --preview
```

See `examples/DEMO_USAGE.md` for detailed walkthroughs!

## 📚 Documentation

- [Quick Reference](docs/QUICK_REFERENCE.md) - Command cheatsheet
- [Tutorial](docs/TUTORIAL.md) - Step-by-step guide
- [Contributing Guide](CONTRIBUTING.md) - How to contribute
- [Architecture](ARCHITECTURE.md) - Technical design
- [Case Study](CASE_STUDY.md) - Real-world testing results
- [False Positive Reduction](docs/FALSE_POSITIVE_REDUCTION.md) - Context-aware analysis features

## 🛠️ Development Status

✅ **Stable Release**: Refactron v1.0.1 is production-ready and actively maintained!

### Current Metrics:

- ✅ 135 tests passing (100% success rate)
- ✅ 84% code coverage
- ✅ 0 critical issues in production code
- ✅ Real-world validated on 5,800+ lines
- ✅ 96.8% analyzer module coverage
- ✅ Comprehensive edge case testing

### Roadmap

**Phase 1: Foundation** ✅ COMPLETE
- Core architecture & CLI
- Configuration system
- Basic analyzers (complexity, code smells)
- Refactoring suggestions with risk scoring
- Before/after code previews

**Phase 2: Advanced Analysis** ✅ COMPLETE
- Security vulnerability scanning
- Dependency analysis
- Dead code detection
- Type hint analysis
- Performance analyzer
- Comprehensive test suite

**Phase 3: Intelligence & Automation** ✅ COMPLETE
- Auto-fix capabilities (14 fixers)
- False positive reduction system
- Context-aware security analysis
- Confidence scoring
- False positive tracking

**Phase 4: Integration & Scale** 📋 PLANNED
- IDE plugins (VS Code, PyCharm)
- Enhanced CI/CD integration
- Multi-file refactoring
- AI-powered pattern recognition
- Historical trend analysis

## 🤝 Contributing

We welcome contributions! Please see:

- [Contributing Guide](CONTRIBUTING.md) - How to contribute
- [Code of Conduct](CODE_OF_CONDUCT.md) - Community guidelines
- [Quick Start Guide](CONTRIBUTING.md#quick-start-5-minutes) - 5-minute setup

Quick setup:

```bash
git clone https://github.com/Refactron-ai/Refactron_lib.git
cd Refactron_lib
bash setup_dev.sh  # macOS/Linux - automatically sets everything up
# OR setup_dev.bat  # Windows
```

## 🧪 CI/CD Status

Refactron uses GitHub Actions for continuous integration and deployment:

- ✅ Automated testing on Python 3.8, 3.9, 3.10, 3.11, 3.12
- ✅ Code quality checks (Black, isort, flake8, mypy)
- ✅ Security scanning with CodeQL
- ✅ Automated dependency updates via Dependabot
- ✅ 84% test coverage maintained
- ✅ Pre-commit hooks for code quality

Check our [Actions page](https://github.com/Refactron-ai/Refactron_lib/actions) for live build status!

## 🔒 Security

Found a security issue? Please report it privately to **security@refactron.us.kg**. See [SECURITY.md](SECURITY.md) for details.

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

**Star ⭐ this repo if you find it helpful!**

**Made with ❤️ for the Python community**
