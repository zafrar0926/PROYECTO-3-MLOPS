#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
NS="mlops-proyecto3"

# Nombre del Job que crea el bucket en MinIO
BUCKET_JOB="minio-create-bucket"

# Funciones de ayuda
apply_if_exists() {
  [[ -f "$1" ]] && {
    echo -e "\n Aplicando $1"
    kubectl apply -f "$1"
  } || echo -e "\n⚠️  No existe: $1 (saltando)"
}

wait_rollout() {
  local kind_name=$1
  echo "⏳ Esperando rollout de $kind_name..."
  kubectl rollout status "$kind_name" -n "$NS"
}

wait_job() {
  local job=$1
  echo "⏳ Esperando fin de Job/$job..."
  kubectl wait --for=condition=complete job/"$job" -n "$NS" --timeout=120s
}

echo "Limpiando Minikube"

minikube stop || true

minikube delete --all || true

docker system prune -af --volumes || true


minikube start

eval $(minikube docker-env)

# 1) Airflow
docker build \
  -t airflow-allinone:latest \
  -f k8s/airflow/Dockerfile \
  .

# 2) Inference API
docker build \
  -t inference-api:latest \
  -f k8s/inference-api/Dockerfile.inference \
  k8s/inference-api

echo "✈️  1) Namespace"
apply_if_exists "$ROOT/k8s/namespace.yml"

echo "✈️ 2) PVCs comunes"
apply_if_exists "$ROOT/k8s/common/storage-pvc.yml"
apply_if_exists "$ROOT/k8s/common/postgres-pvc.yml"
apply_if_exists "$ROOT/k8s/common/postgres-airflow-pvc.yml"

echo "✈️ 3) PostgreSQL para MLflow"
apply_if_exists "$ROOT/k8s/common/postgres-deployment.yml"
apply_if_exists "$ROOT/k8s/common/postgres-service.yml"
wait_rollout "deployment/postgres"

echo "✈️ 4) PostgreSQL para Airflow"
apply_if_exists "$ROOT/k8s/common/postgres-airflow-deployment.yml"
apply_if_exists "$ROOT/k8s/common/postgres-airflow-service.yml"
wait_rollout "deployment/postgres-airflow"

echo "✈️ 5) MinIO"
apply_if_exists "$ROOT/k8s/minio/minio-deployment.yml"
apply_if_exists "$ROOT/k8s/minio/minio-service.yml"
wait_rollout "deployment/minio"

echo "✈️ 6) Creación de bucket en MinIO (Job)"
apply_if_exists "$ROOT/k8s/common/minio-create-bucket-job.yml"
wait_job "$BUCKET_JOB"

echo "✈️ 7) MLflow Server"
apply_if_exists "$ROOT/k8s/mlflow/mlflow-deployment.yml"
apply_if_exists "$ROOT/k8s/mlflow/mlflow-service.yml"
wait_rollout "deployment/mlflow"

echo "✈️ 8) Airflow"
apply_if_exists "$ROOT/k8s/airflow/airflow-db-init-job.yml"
wait_job "airflow-db-init"
apply_if_exists "$ROOT/k8s/airflow/airflow-create-admin-job.yml"


apply_if_exists "$ROOT/k8s/airflow/airflow-deployment.yml"
apply_if_exists "$ROOT/k8s/airflow/airflow-service.yml"
wait_rollout "deployment/airflow"

echo "✅ Fase 1 completada: Infra y Airflow están arriba."
echo "   Ahora ejecuta ./run_pipelines.sh para procesar tus DAGs."
