import os
from pathlib import Path
import uuid

import requests
from PIL import Image, ImageDraw


USE_REAL_MAMT2 = os.getenv("USE_REAL_MAMT2", "false").lower() == "true"
MAMT2_WORKER_URL = os.getenv("MAMT2_WORKER_URL", "http://127.0.0.1:9000")
WORKER_TIMEOUT_SECONDS = 120
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

if USE_REAL_MAMT2:
    print(f"[infer_mamt2] USE_REAL_MAMT2=true, using worker: {MAMT2_WORKER_URL}")
else:
    print("[infer_mamt2] USE_REAL_MAMT2=false, using mock predictor")


def predict_image_mock(image_path: str) -> dict:
    """
    Local mock Mask R-CNN / MAMT2 inference.

    This keeps the original development behavior for local UI/API testing when
    USE_REAL_MAMT2 is not enabled.
    """
    image_path = Path(image_path)

    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    result_filename = f"result_{uuid.uuid4().hex}{image_path.suffix}"
    result_path = output_dir / result_filename

    image = Image.open(image_path).convert("RGB")
    width, height = image.size

    # Generate a size-aware mock bbox so it remains visible on different images.
    x1 = int(width * 0.25)
    y1 = int(height * 0.25)
    x2 = int(width * 0.80)
    y2 = int(height * 0.80)

    box = [x1, y1, x2, y2]
    label = "spalling"
    score = 0.92

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    mask_polygon = [
        (int(width * 0.30), int(height * 0.30)),
        (int(width * 0.72), int(height * 0.28)),
        (int(width * 0.78), int(height * 0.48)),
        (int(width * 0.66), int(height * 0.74)),
        (int(width * 0.38), int(height * 0.78)),
        (int(width * 0.22), int(height * 0.55)),
    ]

    overlay_draw.polygon(mask_polygon, fill=(255, 0, 0, 90))
    result = Image.alpha_composite(image.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(result)
    draw.rectangle(box, outline=(255, 0, 0, 255), width=max(2, width // 150))

    text = f"{label} {score:.2f}"
    text_x = x1
    text_y = max(0, y1 - 24)

    text_box = draw.textbbox((text_x, text_y), text)
    draw.rectangle(text_box, fill=(255, 0, 0, 180))
    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255))

    result = result.convert("RGB")
    result.save(result_path)

    return {
        "boxes": [box],
        "labels": [label],
        "scores": [score],
        "masks": [
            {
                "type": "polygon",
                "points": [[x, y] for x, y in mask_polygon],
            }
        ],
        "result_image_path": str(result_path),
        "result_filename": result_filename,
    }


def predict_image_via_worker(image_path: str) -> dict:
    """Call the standalone MAMT2 Worker HTTP service for real inference."""
    worker_url = MAMT2_WORKER_URL.rstrip("/")
    endpoint = f"{worker_url}/predict"
    payload = {
        "image_path": str(Path(image_path).resolve()),
        "output_dir": str(OUTPUT_DIR).replace("\\", "/"),
    }

    print(
        "[infer_mamt2] worker request "
        f"url={worker_url} image_path={payload['image_path']} output_dir={payload['output_dir']}"
    )

    try:
        response = requests.post(endpoint, json=payload, timeout=WORKER_TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        raise RuntimeError(
            f"MAMT2 Worker request timed out after {WORKER_TIMEOUT_SECONDS}s: {endpoint}"
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Failed to call MAMT2 Worker at {endpoint}. Is the worker service running?"
        ) from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"MAMT2 Worker returned HTTP {response.status_code}: {response.text}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"MAMT2 Worker returned non-JSON response: {response.text}") from exc

    if data.get("status") != "success":
        raise RuntimeError(f"MAMT2 Worker returned unsuccessful response: {data}")

    required_keys = [
        "boxes",
        "labels",
        "scores",
        "masks",
        "result_image_path",
        "result_filename",
    ]
    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        raise RuntimeError(f"MAMT2 Worker response missing keys: {missing_keys}")

    return {key: data[key] for key in required_keys}


def predict_image(image_path: str) -> dict:
    if USE_REAL_MAMT2:
        return predict_image_via_worker(image_path)
    return predict_image_mock(image_path)
