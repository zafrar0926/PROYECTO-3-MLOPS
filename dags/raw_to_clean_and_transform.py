# raw_to_clean_and_transform.py
import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

# Parámetros generales
DATA_ROOT     = '/opt/airflow/data/Diabetes'
DATA_FILENAME = 'Diabetes.csv'
DATA_FILEPATH = os.path.join(DATA_ROOT, DATA_FILENAME)
FILE_ID       = '1k5-1caezQ3zWJbKaiMULTGq-3sz6uThC'
DOWNLOAD_URL  = f'https://docs.google.com/uc?export=download&confirm=&id={FILE_ID}'
BATCH_SIZE    = 15_000

# Columnas explícitas a eliminar antes del split
DROP_COLS = [
    "encounter_id", "patient_nbr",
    "weight", "examide", "citoglipton"
]

# Proporciones para train / val / test
SUBSET_RATIOS = [0.7, 0.15, 0.15]

# Mapa de age → mediana
AGE_MAP = {
    "[0-10)": 5, "[10-20)": 15, "[20-30)": 25, "[30-40)": 35, "[40-50)": 45,
    "[50-60)": 55, "[60-70)": 65, "[70-80)": 75, "[80-90)": 85, "[90-100)": 95
}

# Variables finales a mantener
FINAL_COLUMNS = [
    'time_in_hospital', 'num_lab_procedures', 'num_procedures',
    'num_medications', 'number_outpatient', 'number_emergency',
    'number_inpatient', 'number_diagnoses', 'age'
]

def download_raw_data(**context):
    os.makedirs(DATA_ROOT, exist_ok=True)
    if not os.path.isfile(DATA_FILEPATH):
        r = requests.get(DOWNLOAD_URL, stream=True)
        r.raise_for_status()
        with open(DATA_FILEPATH, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        print(f"✅ Dataset descargado en {DATA_FILEPATH}")
    else:
        print(f"ℹ️ Dataset ya presente en {DATA_FILEPATH}")

def prepare_tables(**context):
    df = pd.read_csv(DATA_FILEPATH)
    df.columns = [c.replace('-', '_') for c in df.columns]
    df = df.drop(columns=[c for c in DROP_COLS if c in df.columns], errors='ignore')
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)

    n = len(df)
    n_train = int(SUBSET_RATIOS[0] * n)
    n_val   = n_train + int(SUBSET_RATIOS[1] * n)

    subsets = {
        'clean_data':       df.iloc[:n_train],
        'clean_validation': df.iloc[n_train:n_val],
        'clean_test':       df.iloc[n_val:]
    }

    pg = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg.get_conn()
    cur  = conn.cursor()

    for tbl, subset_df in subsets.items():
        cur.execute(f"DROP TABLE IF EXISTS {tbl};")
        cols = subset_df.columns.tolist()
        sample = subset_df.head(1)
        col_defs = [
            f"{c} {'INTEGER' if pd.api.types.is_integer_dtype(sample[c]) else 'DOUBLE PRECISION' if pd.api.types.is_float_dtype(sample[c]) else 'TEXT'}"
            for c in cols
        ]
        ddl = f"CREATE TABLE {tbl} (\n  id SERIAL PRIMARY KEY,\n  " + ",\n  ".join(col_defs) + "\n);"
        cur.execute(ddl)
        conn.commit()

        insert_sql = (
            f"INSERT INTO {tbl} ({','.join(cols)}) "
            f"VALUES ({','.join(['%s']*len(cols))})"
        )
        tuples = [tuple(r) for r in subset_df.itertuples(index=False, name=None)]
        if tbl == 'clean_data':
            for start in range(0, len(tuples), BATCH_SIZE):
                batch = tuples[start:start+BATCH_SIZE]
                cur.executemany(insert_sql, batch)
                conn.commit()
                print(f"✅ Batch train {start}-{start+len(batch)-1} insertado en {tbl}")
        else:
            cur.executemany(insert_sql, tuples)
            conn.commit()
            print(f"✅ {tbl} insertada con {len(tuples)} registros")

def transform_features(**context):
    pg   = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg.get_conn()
    cur  = conn.cursor()
    engine = pg.get_sqlalchemy_engine()

    for subset in ['clean_data', 'clean_validation', 'clean_test']:
        df = pd.read_sql(f"SELECT * FROM {subset}", engine)
        df.drop(columns=['id'], errors='ignore', inplace=True)

        df.replace("?", np.nan, inplace=True)
        df['age'] = df['age'].map(AGE_MAP)
        for d in ['diag_1', 'diag_2', 'diag_3']:
            df[d] = df[d].fillna('Missing').astype(str)
        df['diag'] = df['diag_1'] + '_' + df['diag_2'] + '_' + df['diag_3']
        df.drop(columns=['diag_1', 'diag_2', 'diag_3'], inplace=True)

        df['readmitted_flag'] = df['readmitted'].apply(lambda x: 1 if x == '<30' else 0)
        df.drop(columns=['readmitted'], inplace=True)

        # Filtrar solo columnas finales + target
        df = df[FINAL_COLUMNS + ['readmitted_flag']]

        feat_table = subset.replace('clean_', 'features_clean_')
        cur.execute(f"DROP TABLE IF EXISTS {feat_table};")
        conn.commit()

        cols = df.columns.tolist()
        sample = df.head(1)
        col_defs = [
            f"{c} {'INTEGER' if pd.api.types.is_integer_dtype(sample[c]) else 'DOUBLE PRECISION' if pd.api.types.is_float_dtype(sample[c]) else 'TEXT'}"
            for c in cols
        ]
        ddl = f"CREATE TABLE {feat_table} (\n  id SERIAL PRIMARY KEY,\n  " + ",\n  ".join(col_defs) + "\n);"
        cur.execute(ddl)
        conn.commit()

        insert_sql = (
            f"INSERT INTO {feat_table} ({','.join(cols)}) "
            f"VALUES ({','.join(['%s']*len(cols))})"
        )
        tuples = [tuple(r) for r in df.itertuples(index=False, name=None)]
        cur.executemany(insert_sql, tuples)
        conn.commit()
        print(f"✅ {feat_table} creada con {len(tuples)} registros")

# DAG definition
default_args = {
    'owner': 'airflow',
    'start_date': datetime(2025, 5, 1),
    'retries': 1,
    'depends_on_past': False,
}

with DAG(
    dag_id='raw_to_clean_and_transform',
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False,
    tags=['etl', 'batch', 'transform'],
    max_active_runs=1,
) as dag:

    t1 = PythonOperator(
        task_id='download_raw_data',
        python_callable=download_raw_data,
    )
    t2 = PythonOperator(
        task_id='prepare_tables',
        python_callable=prepare_tables,
    )
    t3 = PythonOperator(
        task_id='transform_features',
        python_callable=transform_features,
    )

    t1 >> t2 >> t3

