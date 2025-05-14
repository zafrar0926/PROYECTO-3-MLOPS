# k8s/airflow/airflow_local_settings.py

from airflow.config_templates.airflow_local_settings import DEFAULT_LOGGING_CONFIG
LOGGING_CONFIG = DEFAULT_LOGGING_CONFIG.copy()

# Habilita Remote Logging a MinIO
LOGGING_CONFIG['handlers']['s3_task_handler'] = {
    'class': 'airflow.providers.amazon.aws.log.s3_task_handler.S3TaskHandler',
    'base_log_folder': '/opt/airflow/logs',
    's3_log_folder': 'logs',
    'filename_template': '{{ ti.dag_id }}/{{ ti.task_id }}/{{ ts }}/{{ try_number }}.log',
    's3_bucket': 'mlflow',
    's3_endpoint_url': 'http://minio:9000',
    's3_log_conn_id': 'minio-s3',
}
LOGGING_CONFIG['root']['handlers'].append('s3_task_handler')
