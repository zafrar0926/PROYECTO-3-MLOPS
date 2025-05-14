#!/usr/bin/env bash
set -euo pipefail

NS="mlops-proyecto3"
DATE="$(date +%Y-%m-%d)"
AIRFLOW_LABEL="app=airflow"
MLFLOW_LABEL="app=mlflow"

eval $(minikube docker-env)

# 1) Airflow
docker build \
  -t airflow-allinone:latest \
  -f k8s/airflow/Dockerfile \
  .

kubectl apply -f k8s/airflow/airflow-deployment.yml
kubectl rollout restart deployment airflow -n mlops-proyecto3
kubectl rollout status deployment airflow -n mlops-proyecto3

echo "▶ 1) Localizar pod de Airflow"
AIRFLOW_POD=$(kubectl get pod -n "$NS" -l "$AIRFLOW_LABEL" \
   -o jsonpath="{.items[0].metadata.name}")
echo "   → $AIRFLOW_POD"

run_test() {
  local dag_id=$1
  echo -e "\n▶ Ejecutando test del DAG '$dag_id' ($DATE)…"
  kubectl exec -n "$NS" "$AIRFLOW_POD" -- bash -lc \
    "airflow dags test $dag_id $DATE"
  echo "   ✅ $dag_id OK"
}

run_test raw_to_clean_and_transform
#run_test test_mlflow_connection
run_test train_and_register_mlflow

echo -e "\n▶ Todos los DAGs pasaron el test."

echo -e "\n▶ 2) Verificando modelo en MLflow"
MLFLOW_POD=$(kubectl get pod -n "$NS" -l "$MLFLOW_LABEL" \
   -o jsonpath="{.items[0].metadata.name}")
echo "   → $MLFLOW_POD"

kubectl exec -n "$NS" "$MLFLOW_POD" -- python3 - << 'EOF'
import sys
from mlflow.tracking import MlflowClient

client = MlflowClient()
versions = client.get_latest_versions("DiabetesReadmissionModel")
if not versions:
    print("❌ No se encontró DiabetesReadmissionModel")
    sys.exit(1)

print("✅ Versiones:", [v.version for v in versions])
prod = [v.version for v in versions if v.current_stage=="Production"]
print("✅ En Production:", prod or "ninguna")
sys.exit(0)
EOF

echo -e "\n🎉 ¡Pipelines completados y modelo listo!"
