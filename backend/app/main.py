from pathlib import Path
import uuid

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.infer_mamt2 import predict_image


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
