# BTMS Test Suite

Three-layer testing framework for the Battery Thermal Management System.

```
tests/
├── keyword_driven/      # Keyword-Driven Testing (KDT)
│   ├── keywords.py          — reusable action library
│   ├── test_suite.csv       — test cases as keyword tables
│   └── runner.py            — CSV → execute → report
│
├── data_driven/         # Data-Driven Testing (DDT)
│   ├── test_cfd_engine.py   — parametric pytest suite for CFD heuristics
│   ├── test_ingestion.py    — parametric pytest suite for ingestion service
│   ├── datasets/
│   │   ├── cfd_cases.csv    — CFD input/expected-output table
│   │   └── ingestion_cases.csv
│
└── synthetic/           # Synthetic Data Generation (AI-driven)
    ├── generator.py         — AI synthetic telemetry generator
    ├── generated/           — output JSON datasets land here
    └── validate_synthetic.py — validate generated data quality
```

## Quick start

```bash
cd /Users/shashanksathish/BTMS

# Install test dependencies
pip install pytest pytest-html faker tabulate colorama

# 1. Keyword-Driven Tests
python tests/keyword_driven/runner.py

# 2. Data-Driven Tests (pytest)
pytest tests/data_driven/ -v --html=tests/reports/ddt_report.html

# 3. Generate synthetic data + validate
python tests/synthetic/generator.py
python tests/synthetic/validate_synthetic.py
```
