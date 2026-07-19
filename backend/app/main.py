from pathlib import Path
import time
import uuid

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.infer_mamt2 import predict_image
from app.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    REGISTRY,
)


app = FastAPI(title="MAMT2 Cloud SHM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.middleware("http")
async def record_http_metrics(request: Request, call_next):
    # Prometheus scrapes are intentionally excluded from the business HTTP series.
    if request.url.path == "/metrics":
        return await call_next(request)

    method = request.method
    started_at = time.perf_counter()
    status_code = 500
    HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_template = getattr(route, "path", "unmatched")
        if not route_template:
            route_template = "unmatched"

        try:
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                route=route_template,
                status_code=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                route=route_template,
            ).observe(time.perf_counter() - started_at)
        finally:
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
def health_check():
    return {
        "message": "MAMT2 Cloud SHM API is running"
    }


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    image_filename = f"{uuid.uuid4().hex}{suffix}"
    image_path = UPLOAD_DIR / image_filename

    with image_path.open("wb") as f:
        content = await file.read()
        f.write(content)

    result = predict_image(str(image_path))
    result_url = f"/results/{result['result_filename']}"

    return {
        "status": "success",
        "input_filename": image_filename,
        "boxes": result["boxes"],
        "labels": result["labels"],
        "scores": result["scores"],
        "masks": result.get("masks", []),
        "result_image_path": result.get("result_image_path", ""),
        "result_filename": result["result_filename"],
        "result_url": result_url,
        "result_image_url": f"/api{result_url}",
    }


@app.get("/results/{filename}")
def get_result_image(filename: str):
    image_path = OUTPUT_DIR / filename

    if not image_path.exists():
        return {
            "status": "error",
            "message": "result image not found"
        }

    return FileResponse(image_path)
