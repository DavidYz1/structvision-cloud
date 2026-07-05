from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from worker.mamt2_predictor import predict_image_with_mamt2  # noqa: E402


app = FastAPI(title="MAMT2 Worker", version="0.1.0")


class PredictRequest(BaseModel):
    image_path: str
    output_dir: Optional[str] = None


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "service": "mamt2-worker",
    }


@app.post("/predict")
def predict(request: PredictRequest) -> dict:
    try:
        result = predict_image_with_mamt2(
            image_path=request.image_path,
            output_dir=request.output_dir,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"MAMT2 worker inference failed: {exc}",
        ) from exc

    result_filename = result.get("result_filename", "")
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


@app.post("/predict-file")
async def predict_file(file: UploadFile = File(...)) -> dict:
    try:
        suffix = Path(file.filename or "input.jpg").suffix or ".jpg"
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            temp_image_path = temp_dir / f"input{suffix}"
            temp_image_path.write_bytes(await file.read())

            result = predict_image_with_mamt2(
                image_path=str(temp_image_path),
                output_dir=str(temp_dir),
            )

            result_image_path = Path(result["result_image_path"])
            result_image_base64 = base64.b64encode(result_image_path.read_bytes()).decode("ascii")

            return {
                "status": "success",
                "boxes": result.get("boxes", []),
                "labels": result.get("labels", []),
                "scores": result.get("scores", []),
                "masks": result.get("masks", []),
                "result_filename": result.get("result_filename", ""),
                "result_image_base64": result_image_base64,
            }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"MAMT2 worker file inference failed: {exc}",
        ) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=9000)
