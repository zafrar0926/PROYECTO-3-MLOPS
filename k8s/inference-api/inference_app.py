import os
import time
import pandas as pd
import mlflow.pyfunc
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from typing import List, Dict, Any
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# --- Configuración de entorno ---
MLFLOW_MODEL_NAME = os.getenv("MLFLOW_MODEL_NAME", "DiabetesReadmissionModel")
MLFLOW_MODEL_STAGE = os.getenv("MLFLOW_MODEL_STAGE", "Production")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI")

if not MLFLOW_TRACKING_URI:
    raise RuntimeError("❌ Debes definir MLFLOW_TRACKING_URI")

os.environ["MLFLOW_TRACKING_URI"] = MLFLOW_TRACKING_URI

# --- Carga del modelo desde MLflow ---
model_uri = f"models:/{MLFLOW_MODEL_NAME}/{MLFLOW_MODEL_STAGE}"
model = mlflow.pyfunc.load_model(model_uri)

# --- Columnas esperadas por el modelo ---
MODEL_COLUMNS: List[str] = [
    "time_in_hospital", "num_lab_procedures", "num_procedures",
    "num_medications", "number_outpatient", "number_emergency",
    "number_inpatient", "number_diagnoses", "age"
]

# --- Setup de FastAPI ---
app = FastAPI(title="Inference API")

# --- Métricas Prometheus ---
REQUEST_COUNT = Counter(
    "inference_requests_total", "Total de peticiones de inferencia", ["endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "inference_request_latency_seconds", "Latencia de petición de inferencia", ["endpoint"]
)

# --- Esquema de entrada ---
class PredictionRequest(BaseModel):
    instances: List[Dict[str, Any]]

# --- Endpoint de predicción ---
@app.post("/predict")
async def predict(payload: PredictionRequest):
    start = time.time()
    status = "success"
    try:
        df = pd.DataFrame(payload.instances)

        # Validar presencia de columnas requeridas
        missing_cols = [col for col in MODEL_COLUMNS if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Faltan columnas requeridas: {missing_cols}")

        # Reordenar columnas y convertir a tipo numérico
        df = df[MODEL_COLUMNS]
        df = df.apply(pd.to_numeric, errors="raise")

        preds = model.predict(df).tolist()
        return {"predictions": preds}

    except Exception as e:
        status = "error"
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        REQUEST_COUNT.labels(endpoint="/predict", status=status).inc()
        REQUEST_LATENCY.labels(endpoint="/predict").observe(time.time() - start)

# --- Endpoint para Prometheus ---
@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
