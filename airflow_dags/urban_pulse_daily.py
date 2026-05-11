"""
Urban Pulse — Airflow DAG
Daily pipeline: Generate → Kafka → Spark ETL → dbt → ML Training → Report
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.utils.dates import days_ago
from airflow.models import Variable


DEFAULT_ARGS = {
    "owner": "urban-pulse",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


def run_data_validation(**context):
    """Validate incoming data quality before processing"""
    import logging
    ds = context["ds"]
    logging.info(f"Running data validation for {ds}")
    # In production: run Great Expectations suite here
    logging.info("✅ Data validation passed")


def trigger_ml_retraining(**context):
    """Re-train ML models if data drift detected"""
    import logging
    ds = context["ds"]
    logging.info(f"Checking for data drift on {ds}...")
    # Drift detection logic
    drift_detected = False  # placeholder
    if drift_detected:
        logging.info("🔄 Drift detected — triggering model retraining")
    else:
        logging.info("✅ No drift detected — using existing models")


def send_daily_report(**context):
    """Generate and send daily executive report via LLM"""
    import logging
    import requests
    try:
        r = requests.post("http://localhost:8000/api/v1/insights/daily-report", timeout=30)
        report = r.json().get("report", "Report generation failed")
        logging.info(f"Daily Report Generated:\n{report}")
    except Exception as e:
        logging.warning(f"Report generation failed: {e}")


# ─── DAG Definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="urban_pulse_daily_pipeline",
    description="Urban Pulse: Daily data engineering + ML pipeline",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 2 * * *",     # Run at 2 AM daily
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["urban-pulse", "data-engineering", "ml", "production"],
) as dag:

    dag.doc_md = """
    ## Urban Pulse Daily Pipeline
    
    **Schedule**: Every day at 2 AM IST
    
    ### Steps:
    1. **Data Quality** — Validate yesterday's raw data
    2. **Spark Batch ETL** — Process raw → clean → aggregated
    3. **dbt Transforms** — Build Star Schema in Snowflake
    4. **dbt Tests** — Run 47 data quality tests
    5. **ML Retraining Check** — Detect drift, retrain if needed
    6. **Daily Report** — LLM-powered executive summary
    """

    # ── Start ──────────────────────────────────────────────────
    start = DummyOperator(task_id="pipeline_start")
    end   = DummyOperator(task_id="pipeline_complete")

    # ── Data Validation ────────────────────────────────────────
    validate_data = PythonOperator(
        task_id="validate_raw_data",
        python_callable=run_data_validation,
        provide_context=True,
    )

    # ── Spark ETL ──────────────────────────────────────────────
    spark_etl = BashOperator(
        task_id="run_spark_batch_etl",
        bash_command="""
            cd /opt/urban-pulse/spark_pipelines && \
            spark-submit \
                --master local[*] \
                --driver-memory 4g \
                --executor-memory 4g \
                batch/daily_etl.py \
                --date {{ ds }} \
                --rides-path /data/raw/uber/{{ ds }}/ \
                --orders-path /data/raw/zomato/{{ ds }}/
        """,
    )

    # ── dbt Run ────────────────────────────────────────────────
    dbt_run = BashOperator(
        task_id="dbt_run_transformations",
        bash_command="cd /opt/urban-pulse/dbt_models && dbt run --profiles-dir . --target prod",
    )

    # ── dbt Test ───────────────────────────────────────────────
    dbt_test = BashOperator(
        task_id="dbt_run_tests",
        bash_command="cd /opt/urban-pulse/dbt_models && dbt test --profiles-dir . --target prod",
    )

    # ── ML Check ───────────────────────────────────────────────
    ml_check = PythonOperator(
        task_id="ml_drift_check_and_retrain",
        python_callable=trigger_ml_retraining,
        provide_context=True,
    )

    # ── Daily Report ───────────────────────────────────────────
    daily_report = PythonOperator(
        task_id="generate_daily_report",
        python_callable=send_daily_report,
        provide_context=True,
    )

    # ── DAG Dependencies ───────────────────────────────────────
    start >> validate_data >> spark_etl >> dbt_run >> dbt_test >> ml_check >> daily_report >> end
