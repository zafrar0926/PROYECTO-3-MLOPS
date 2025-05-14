#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
NS="mlops-proyecto3"

echo "🔁 Reiniciando entorno de observabilidad..."

# 0. Limpiar recursos previos
echo "🧹 Eliminando despliegues anteriores..."
kubectl delete deployment inference-api grafana prometheus -n "$NS" --ignore-not-found
kubectl delete svc inference-api grafana prometheus -n "$NS" --ignore-not-found
kubectl delete configmap grafana-datasources grafana-dashboard grafana-dashboard-provider prometheus-config -n "$NS" --ignore-not-found

echo
echo "⏳ Esperando 5s antes del redeploy..."
sleep 5

# 1. Aplicar configmaps
echo "📦 Aplicando ConfigMaps..."
kubectl apply -f "$ROOT/k8s/observability/prometheus-configmap.yml"
kubectl apply -f "$ROOT/k8s/observability/grafana-datasources.yml"
kubectl apply -f "$ROOT/k8s/observability/grafana-dashboard-provider.yml"
kubectl apply -f "$ROOT/k8s/observability/grafana-dashboard-configmap.yml"

# 2. Desplegar servicios
echo "🚀 Desplegando Inference API, Prometheus y Grafana..."
kubectl apply -f "$ROOT/k8s/inference-api/inference-api.yml"
kubectl apply -f "$ROOT/k8s/observability/prometheus-deployment.yml"
kubectl apply -f "$ROOT/k8s/observability/grafana-deployment.yml"

# 3. Esperar a que estén listos
kubectl rollout status deployment/inference-api -n "$NS"
kubectl rollout status deployment/prometheus -n "$NS"
kubectl rollout status deployment/grafana -n "$NS"

echo "✅ Todos los deployments están listos."

echo
echo "🔌 Iniciando PORT-FORWARDS..."

start_port_forward() {
  local svc="$1"
  local local_port="$2"
  local target_port="$3"
  local name="$4"

  if lsof -i TCP:"$local_port" &>/dev/null; then
    echo "  ⚠️  $name ($local_port) YA está ocupado."
  else
    kubectl port-forward svc/"$svc" "$local_port":"$target_port" -n "$NS" &>/dev/null &
    echo "  • $name ($local_port) → http://localhost:$local_port"
  fi
}

start_port_forward inference-api 8081 80 "Inference API"
start_port_forward airflow       8080 8080 "Airflow"
start_port_forward mlflow        5000 5000 "MLflow"
start_port_forward prometheus    9090 9090 "Prometheus"
start_port_forward grafana       3000 3000 "Grafana"

echo
echo "🎯 Visita Grafana en http://localhost:3000"
echo "     Usuario: admin   Contraseña: admin"
echo "     Dashboard: Monitoreo (precargado)"
