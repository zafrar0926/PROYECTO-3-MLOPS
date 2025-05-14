# k8s/airflow/entrypoint.sh
#!/usr/bin/env bash
set -e

airflow db init
airflow connections create-default-connections || true

# Crea admin/admin si no existe (o ignora si ya existe)
airflow users create \
  --username admin \
  --firstname admin \
  --lastname admin \
  --role Admin \
  --email admin@example.com \
  --password admin || true

airflow scheduler &
exec airflow webserver --hostname 0.0.0.0 --port 8080
