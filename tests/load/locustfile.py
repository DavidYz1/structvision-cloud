"""Locust workload for the browser-facing GPU inference endpoint."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

from locust import HttpUser, constant, task


INFERENCE_PATH = "/api/predict"
INFERENCE_REQUEST_NAME = "GPU inference"
REQUEST_TIMEOUT_SECONDS = 120
MAX_FAILURE_DETAIL_LENGTH = 200

REQUIRED_STRING_FIELDS = (
    "input_filename",
    "result_image_path",
    "result_filename",
    "result_url",
    "result_image_url",
)
REQUIRED_LIST_FIELDS = ("boxes", "labels", "scores", "masks")


def _short_text(value: Any) -> str:
    text = " ".join(str(value).split())
    if len(text) <= MAX_FAILURE_DETAIL_LENGTH:
        return text
    return f"{text[:MAX_FAILURE_DETAIL_LENGTH]}..."


def _resolve_image_path() -> Path:
    configured_path = os.environ.get("LOCUST_IMAGE_PATH", "").strip()
    if not configured_path:
        raise SystemExit(
            "Load test configuration error: LOCUST_IMAGE_PATH is required "
            "and must point to a readable test image."
        )

    image_path = Path(configured_path).expanduser()
    if not image_path.is_file():
        raise SystemExit(
            "Load test configuration error: LOCUST_IMAGE_PATH does not "
            f"point to a file: {image_path}"
        )

    try:
        with image_path.open("rb") as image_file:
            if not image_file.read(1):
                raise SystemExit(
                    "Load test configuration error: LOCUST_IMAGE_PATH "
                    f"points to an empty file: {image_path}"
                )
    except OSError as exc:
        raise SystemExit(
            "Load test configuration error: LOCUST_IMAGE_PATH cannot be "
            f"read: {image_path} ({_short_text(exc)})"
        ) from exc

    return image_path.resolve()


def _response_failure(response: Any) -> str | None:
    status_code = getattr(response, "status_code", None) or 0
    if not 200 <= status_code < 300:
        detail = _short_text(
            response.text or getattr(response, "error", "no response body")
        )
        return f"HTTP {status_code}: {detail}"

    if status_code != 200:
        return f"unexpected successful HTTP status: {status_code}"

    content_type = response.headers.get("Content-Type", "")
    media_type = content_type.partition(";")[0].strip().lower()
    if media_type != "application/json":
        return f"unexpected Content-Type: {_short_text(content_type or 'missing')}"

    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        return f"invalid JSON response: {_short_text(exc)}"

    if not isinstance(payload, dict):
        return f"response JSON must be an object, got {type(payload).__name__}"

    if payload.get("status") != "success":
        detail = payload.get(
            "message",
            payload.get("detail", payload.get("status")),
        )
        return f"business status is not success: {_short_text(detail)}"

    missing_fields = sorted(
        field
        for field in (*REQUIRED_STRING_FIELDS, *REQUIRED_LIST_FIELDS)
        if field not in payload
    )
    if missing_fields:
        return f"missing result fields: {', '.join(missing_fields)}"

    invalid_string_fields = [
        field
        for field in REQUIRED_STRING_FIELDS
        if not isinstance(payload[field], str) or not payload[field]
    ]
    if invalid_string_fields:
        return f"invalid string fields: {', '.join(invalid_string_fields)}"

    invalid_list_fields = [
        field
        for field in REQUIRED_LIST_FIELDS
        if not isinstance(payload[field], list)
    ]
    if invalid_list_fields:
        return f"invalid list fields: {', '.join(invalid_list_fields)}"

    return None


IMAGE_PATH = _resolve_image_path()
IMAGE_CONTENT_TYPE = (
    mimetypes.guess_type(IMAGE_PATH.name)[0] or "application/octet-stream"
)


class GpuInferenceUser(HttpUser):
    """Continuously submit the same image to the real browser API."""

    wait_time = constant(0)

    def on_start(self) -> None:
        try:
            self.image_data = IMAGE_PATH.read_bytes()
        except OSError as exc:
            raise RuntimeError(
                f"Failed to read LOCUST_IMAGE_PATH for virtual user: {IMAGE_PATH}"
            ) from exc

    @task
    def predict_image(self) -> None:
        files = {
            "file": (
                IMAGE_PATH.name,
                self.image_data,
                IMAGE_CONTENT_TYPE,
            )
        }
        with self.client.post(
            INFERENCE_PATH,
            files=files,
            name=INFERENCE_REQUEST_NAME,
            timeout=REQUEST_TIMEOUT_SECONDS,
            catch_response=True,
        ) as response:
            failure = _response_failure(response)
            if failure:
                response.failure(failure)
            else:
                response.success()
