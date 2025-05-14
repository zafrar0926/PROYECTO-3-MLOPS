# dags/test_mlflow_connection.py

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import mlflow

def test_mlflow():
    mlflow.set_tracking_uri("http://mlflow:5000")
    # set_experiment crea el experimento solo si no existe
    mlflow.set_experiment("airflow-connection-test")
    with mlflow.start_run():
        mlflow.log_param("tested_at", datetime.utcnow().isoformat())
        mlflow.log_metric("value", 42)
    print("✅ MLflow connectivity OK")

with DAG(
    dag_id="test_mlflow_connection",
    start_date=datetime(2025, 5, 9),
    schedule_interval=None,
    catchup=False,
) as dag:
    PythonOperator(
        task_id="connect_and_log",
        python_callable=test_mlflow
    )

