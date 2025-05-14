FROM apache/airflow:2.8.1-python3.10

USER root

# Instala psycopg2, mlflow, boto3, imbalanced-learn y xgboost como usuario airflow
RUN su airflow -s /bin/bash -c "pip install psycopg2-binary mlflow boto3 imbalanced-learn xgboost"

# Copia tus DAGs
COPY dags/ /opt/airflow/dags/

# Copia la configuración de logging remoto
COPY k8s/airflow/airflow_local_settings.py /opt/airflow/airflow_local_settings.py

# Copia el entrypoint y dale permisos
COPY k8s/airflow/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER airflow
ENTRYPOINT ["/entrypoint.sh"]

