import os
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from mlflow import set_tracking_uri, set_experiment, start_run
from mlflow.tracking import MlflowClient
import mlflow.xgboost

MLFLOW_EXPERIMENT = "diabetes_readmission"
TRAIN_TABLE       = "features_clean_data"
TEST_TABLE        = "features_clean_test"
POSTGRES_CONN     = "postgres_default"

def train_and_register(**context):
    import pandas as pd
    import xgboost as xgb
    from sklearn.metrics import f1_score, roc_auc_score, precision_score, recall_score
    from imblearn.under_sampling import RandomUnderSampler
    from mlflow.models.signature import infer_signature

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    set_tracking_uri(tracking_uri)
    set_experiment(MLFLOW_EXPERIMENT)
    client = MlflowClient()

    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN)
    engine = hook.get_sqlalchemy_engine()
    df_tr = pd.read_sql(f"SELECT * FROM {TRAIN_TABLE}", engine)
    df_te = pd.read_sql(f"SELECT * FROM {TEST_TABLE}", engine)

    target = "readmitted_flag"
    features = [
        'time_in_hospital', 'num_lab_procedures', 'num_procedures',
    'num_medications', 'number_outpatient', 'number_emergency',
    'number_inpatient', 'number_diagnoses', 'age'
    ]

    y_tr = df_tr.pop(target)
    X_tr = df_tr[features]
    y_te = df_te.pop(target)
    X_te = df_te[features]

    for df in [X_tr, X_te]:
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].astype("category").cat.codes

    sampler = RandomUnderSampler(random_state=42)
    Xs, ys = sampler.fit_resample(X_tr, y_tr)

    best_model, best_score, best_params = None, -1, {}

    for n in [50, 100]:
        for d in [3, 5, 10]:
            for lr in [0.05, 0.1]:
                for ss in [0.8, 1.0]:
                    for cs in [0.8, 1.0]:
                        clf = xgb.XGBClassifier(
                            tree_method="hist",
                            use_label_encoder=False,
                            eval_metric="logloss",
                            random_state=101,
                            n_estimators=n,
                            max_depth=d,
                            learning_rate=lr,
                            subsample=ss,
                            colsample_bytree=cs
                        )
                        clf.fit(Xs, ys)
                        preds = clf.predict(X_te)
                        f1 = f1_score(y_te, preds)
                        if f1 > best_score:
                            best_score = f1
                            best_model = clf
                            best_params = {
                                "n_estimators": n,
                                "max_depth": d,
                                "learning_rate": lr,
                                "subsample": ss,
                                "colsample_bytree": cs
                            }

    with start_run(run_name="manual_gridsearch_model"):
        mlflow.log_params(best_params)
        preds = best_model.predict(X_te)
        probs = best_model.predict_proba(X_te)[:, 1]
        mlflow.log_metrics({
            "f1": f1_score(y_te, preds),
            "auc": roc_auc_score(y_te, probs),
            "precision": precision_score(y_te, preds),
            "recall": recall_score(y_te, preds),
        })
        signature = infer_signature(X_te.head(), preds[:5])
        mlflow.xgboost.log_model(
            best_model,
            artifact_path="model",
            signature=signature,
            registered_model_name="DiabetesReadmissionModel"
        )
        latest = client.get_latest_versions("DiabetesReadmissionModel", stages=["None"])
        client.transition_model_version_stage(
            name="DiabetesReadmissionModel",
            version=latest[-1].version,
            stage="Production",
            archive_existing_versions=True,
        )

# DAG
with DAG(
    dag_id="train_and_register_mlflow",
    default_args={
        "owner": "airflow",
        "start_date": datetime(2025, 5, 1),
        "retries": 1,
        "depends_on_past": False,
    },
    schedule_interval=None,
    catchup=False,
    max_active_runs=1,
    tags=["mlflow", "training"],
) as dag:
    PythonOperator(
        task_id="train_and_register",
        python_callable=train_and_register,
        executor_config={
            "KubernetesExecutor": {
                "requestMemory": "1Gi",
                "limitMemory": "2Gi",
                "requestCpu": "1",
                "limitCpu": "2",
                "env": [
                    {"name": "MLFLOW_TRACKING_URI", "value": "{{ var.value.MLFLOW_TRACKING_URI }}"},
                    {"name": "AWS_ACCESS_KEY_ID", "value": "minioadmin"},
                    {"name": "AWS_SECRET_ACCESS_KEY", "value": "minioadmin"},
                    {"name": "MLFLOW_S3_ENDPOINT_URL", "value": "http://minio.mlops-proyecto3.svc.cluster.local:9000"},
                    {"name": "AIRFLOW_CONN_POSTGRES_DEFAULT", "value": "postgresql+psycopg2://airflow:airflow@postgres-airflow:5432/airflow"},
                ]
            }
        },
    )

