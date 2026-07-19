from __future__ import annotations

import base64
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from worker.mamt2_predictor import (  # noqa: E402
    MAMT2InputError,
    MAMT2OutputError,
    get_predictor,
)
from worker.metrics import (  # noqa: E402
    DETECTED_INSTANCES,
    INFERENCE_DURATION_SECONDS,
    INFERENCE_IN_PROGRESS,
    INFERENCE_REQUESTS_TOTAL,
    REGISTRY,
)


app = FastAPI(title="MAMT2 Worker", version="0.1.0")


class PredictRequest(BaseModel):
    image_path: str
    output_dir: Optional[str] = None


def _run_prediction(endpoint: str, image_path: str, output_dir: str | None) -> dict:
    # Lazy model construction happens before the timer, so the first request's
    # model load is represented only by the dedicated model-load histogram.
    predictor = get_predictor()
    started_at = time.perf_counter()
    try:
        return predictor.predict(image_path=image_path, output_dir=output_dir)
    finally:
        INFERENCE_DURATION_SECONDS.labels(endpoint=endpoint).observe(
            time.perf_counter() - started_at
        )


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "service": "mamt2-worker",
    }


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict")
def predict(request: PredictRequest) -> dict:
    endpoint = "/predict"
    result_label = "inference_error"
    INFERENCE_IN_PROGRESS.labels(endpoint=endpoint).inc()

    try:
        try:
            result = _run_prediction(
                endpoint=endpoint,
                image_path=request.image_path,
                output_dir=request.output_dir,
            )
        except MAMT2InputError as exc:
            result_label = "invalid_input"
            raise HTTPException(
                status_code=500,
                detail=f"MAMT2 worker inference failed: {exc}",
            ) from exc
        except MAMT2OutputError as exc:
            result_label = "output_error"
            raise HTTPException(
                status_code=500,
                detail=f"MAMT2 worker inference failed: {exc}",
            ) from exc
        except Exception as exc:  # noqa: BLE001
            result_label = "inference_error"
            raise HTTPException(
                status_code=500,
                detail=f"MAMT2 worker inference failed: {exc}",
            ) from exc

        DETECTED_INSTANCES.labels(endpoint=endpoint).observe(
            len(result.get("boxes", []))
        )
        result_filename = result.get("result_filename", "")
        result_label = "success"
        return {
            "status": "success",
            "boxes": result.get("boxes", []),
            "labels": result.get("labels", []),
            "scores": result.get("scores", []),
            "masks": result.get("masks", []),
            "result_image_path": result.get("result_image_path", ""),
            "result_filename": result_filename,
            "result_url": f"/results/{result_filename}" if result_filename else "",
        }
    finally:
        try:
            INFERENCE_REQUESTS_TOTAL.labels(
                endpoint=endpoint,
                result=result_label,
            ).inc()
        finally:
            INFERENCE_IN_PROGRESS.labels(endpoint=endpoint).dec()


@app.post("/predict-file")
async def predict_file(file: UploadFile = File(...)) -> dict:
    endpoint = "/predict-file"
    result_label = "invalid_input"
    INFERENCE_IN_PROGRESS.labels(endpoint=endpoint).inc()

    try:
        try:
            suffix = Path(file.filename or "input.jpg").suffix or ".jpg"
            with tempfile.TemporaryDirectory() as temp_dir_name:
                temp_dir = Path(temp_dir_name)
                temp_image_path = temp_dir / f"input{suffix}"
                temp_image_path.write_bytes(await file.read())

                result_label = "inference_error"
                result = _run_prediction(
                    endpoint=endpoint,
                    image_path=str(temp_image_path),
                    output_dir=str(temp_dir),
                )
                DETECTED_INSTANCES.labels(endpoint=endpoint).observe(
                    len(result.get("boxes", []))
                )

                result_label = "output_error"
                result_image_path = Path(result["result_image_path"])
                result_image_base64 = base64.b64encode(
                    result_image_path.read_bytes()
                ).decode("ascii")

                response_payload = {
                    "status": "success",
                    "boxes": result.get("boxes", []),
                    "labels": result.get("labels", []),
                    "scores": result.get("scores", []),
                    "masks": result.get("masks", []),
                    "result_filename": result.get("result_filename", ""),
                    "result_image_base64": result_image_base64,
                }
        except MAMT2InputError as exc:
            result_label = "invalid_input"
            raise HTTPException(
                status_code=500,
                detail=f"MAMT2 worker file inference failed: {exc}",
            ) from exc
        except MAMT2OutputError as exc:
            result_label = "output_error"
            raise HTTPException(
                status_code=500,
                detail=f"MAMT2 worker file inference failed: {exc}",
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=f"MAMT2 worker file inference failed: {exc}",
            ) from exc

        result_label = "success"
        return response_payload
    finally:
        try:
            INFERENCE_REQUESTS_TOTAL.labels(
                endpoint=endpoint,
                result=result_label,
            ).inc()
        finally:
            INFERENCE_IN_PROGRESS.labels(endpoint=endpoint).dec()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=9000)
