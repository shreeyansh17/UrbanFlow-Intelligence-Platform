import os
import re


def replace_in_file(path, old, new, label):
    if not os.path.exists(path):
        print(f"SKIP (not found): {path}")
        return
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print(f"SKIP (pattern not found, maybe already fixed): {label}")
        return
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"FIXED: {label}")


# 1. Zomato delivery time cap bug
replace_in_file(
    "data_generators/zomato_generator.py",
    "dist = round(max(0.5, dist + random.uniform(-0.5, 1.5)), 2)",
    "dist = round(min(15.0, max(0.5, dist + random.uniform(-0.5, 1.5))), 2)",
    "zomato distance cap",
)
replace_in_file(
    "data_generators/zomato_generator.py",
    "delivery_time = max(10, base_delivery)",
    "delivery_time = min(90, max(10, base_delivery))",
    "zomato delivery_time cap",
)

# 2. Outdated Claude model string
replace_in_file(
    "ml_models/llm_insights.py",
    'self.model = "claude-sonnet-4-20250514"',
    'self.model = "claude-sonnet-4-6"',
    "Claude model string",
)

# 3. f-string / bare except / unused var cleanups
replace_in_file(
    "data_generators/run_generators.py",
    'print(f"\\n🚗 UBER RIDES")',
    'print("\\n🚗 UBER RIDES")',
    "f-string fix 1",
)
replace_in_file(
    "data_generators/run_generators.py",
    'print(f"\\n🍔 ZOMATO ORDERS")',
    'print("\\n🍔 ZOMATO ORDERS")',
    "f-string fix 2",
)
replace_in_file(
    "data_generators/run_generators.py",
    "uber_csv = save_to_csv",
    "save_to_csv",
    "unused var uber_csv",
)
replace_in_file(
    "data_generators/run_generators.py",
    "zomato_csv = save_to_csv",
    "save_to_csv",
    "unused var zomato_csv",
)
replace_in_file(
    "data_generators/uber_generator.py",
    'f"DRV_UNKNOWN"',
    '"DRV_UNKNOWN"',
    "f-string fix 3",
)
replace_in_file(
    "ml_models/surge_prediction.py",
    'logger.success(f"MODEL RESULTS")',
    'logger.success("MODEL RESULTS")',
    "f-string fix 4",
)
replace_in_file(
    "dashboards/plotly_dashboard.py",
    "    except:\n",
    "    except Exception:\n",
    "bare except fix",
)

# 4. daily_etl.py — log null counts
replace_in_file(
    "spark_pipelines/batch/daily_etl.py",
    '        nulls = {col: df.filter(F.col(col).isNull()).count() for col in df.columns[:8]}\n\n        logger.info(f"\\n{\'=\'*50}")\n        logger.info(f"DQ Report: {name}")\n        logger.info(f"Total rows: {total:,}")',
    '        nulls = {col: df.filter(F.col(col).isNull()).count() for col in df.columns[:8]}\n\n        logger.info(f"\\n{\'=\'*50}")\n        logger.info(f"DQ Report: {name}")\n        logger.info(f"Total rows: {total:,}")\n        logger.info(f"Null counts (first 8 cols): {nulls}")',
    "daily_etl null logging",
)

# 5. Remove dead sample dict in test file
replace_in_file(
    "tests/test_urban_pulse.py",
    '        sample = {\n            "hour": 18,\n            "pickup_zone": 2,\n            "vehicle_type": "UberGo",\n            "distance_km": 8.5,\n            "weather_condition": "Rain",\n            "is_peak_hour": True,\n            "timestamp": datetime.now().isoformat(),\n        }\n        # Direct category prediction (bypass predict method for unit test)\n        assert model.model is not None',
    "        # Direct category prediction (bypass predict method for unit test)\n        assert model.model is not None",
    "remove dead sample var",
)

# 6. Rewrite CI workflow
os.makedirs(".github/workflows", exist_ok=True)
ci_yml = """name: Urban Pulse CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    name: Run Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.10
        uses: actions/setup-python@v4
        with:
          python-version: "3.10"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install pytest pytest-cov pytest-asyncio httpx
          pip install pandas numpy scikit-learn xgboost faker loguru optuna prophet tensorflow anthropic
          pip install fastapi uvicorn pydantic python-dotenv

      - name: Run tests
        run: |
          cd tests
          pytest test_urban_pulse.py -v --tb=short \\
            --cov=.. --cov-report=xml --cov-report=term-missing \\
            -k "not TestAPI"

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  lint:
    name: Code Quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: "3.10"

      - name: Install linters
        run: pip install flake8 black isort

      - name: Check formatting
        run: black --check --diff .

      - name: Check imports
        run: isort --check-only --profile black .

      - name: Lint
        run: flake8 . --max-line-length=120 --ignore=E501,W503,E226,E402,F403,F405,W291,W293,E231

  docker:
    name: Build Docker Images
    runs-on: ubuntu-latest
    needs: [test]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Build API image
        run: docker build -f docker/Dockerfile.api -t urban-pulse-api:${{ github.sha }} .

      - name: Build Dashboard image
        run: docker build -f docker/Dockerfile.dashboard -t urban-pulse-dashboard:${{ github.sha }} .

      - name: Test docker-compose
        run: |
          cp .env.example .env
          docker-compose config

  dbt:
    name: Validate dbt Models
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: "3.10"

      - name: Install dbt
        run: |
          pip install dbt-core==1.7.3 dbt-snowflake==1.7.3 "protobuf<5"

      - name: Validate dbt project
        env:
          SNOWFLAKE_ACCOUNT: dummy_account
          SNOWFLAKE_USER: dummy_user
          SNOWFLAKE_PASSWORD: dummy_password
        run: |
          cd dbt_models
          dbt parse --profiles-dir . --no-send-anonymous-usage-stats
"""
with open(".github/workflows/ci.yml", "w", encoding="utf-8") as f:
    f.write(ci_yml)
print("FIXED: .github/workflows/ci.yml rewritten")

# 7. Add missing dbt sources.yml
os.makedirs("dbt_models/models/staging", exist_ok=True)
sources_yml = """version: 2

sources:
  - name: raw
    schema: RAW
    description: Raw ingested data landed by Spark batch/streaming pipelines
    tables:
      - name: FACT_RIDES
        description: Raw Uber-style ride events
      - name: FACT_ORDERS
        description: Raw Zomato-style food delivery order events
"""
with open("dbt_models/models/staging/sources.yml", "w", encoding="utf-8") as f:
    f.write(sources_yml)
print("FIXED: dbt_models/models/staging/sources.yml created")

# 8. Add missing dbt seed
os.makedirs("dbt_models/seeds", exist_ok=True)
seed_csv = """zone_id,zone_name,latitude,longitude,zone_type,density
1,Andheri West,19.1197,72.8466,residential,high
2,Bandra Kurla,19.0596,72.8650,business,very_high
3,Colaba,18.9067,72.8147,tourist,medium
4,Dadar,19.0178,72.8478,mixed,high
5,Juhu,19.1075,72.8263,premium,medium
6,Lower Parel,18.9956,72.8258,business,high
7,Malad East,19.1871,72.8485,residential,very_high
8,Powai,19.1176,72.9060,tech_hub,high
9,Thane,19.2183,72.9781,suburban,high
10,Borivali,19.2307,72.8567,residential,very_high
11,Navi Mumbai,19.0330,73.0297,planned,medium
12,Airport Zone,19.0896,72.8656,transit,medium
"""
with open("dbt_models/seeds/dim_zone_seed.csv", "w", encoding="utf-8") as f:
    f.write(seed_csv)
print("FIXED: dbt_models/seeds/dim_zone_seed.csv created")

print("\nDone. Now run: python -m pip install --quiet black isort autoflake flake8")
print(
    "Then: python -m autoflake --in-place --remove-all-unused-imports --remove-unused-variables --recursive ."
)
print("Then: python -m isort --profile black .")
print("Then: python -m black .")
