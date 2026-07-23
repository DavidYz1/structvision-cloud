from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from app import infer_mamt2
from app.main import app, health_check, metrics


class FakeWorkerResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self.payload = payload
        self.text = "" if payload is None else str(payload)

    def json(self) -> dict:
        if self.payload is None:
            raise ValueError("response has no JSON body")
        return self.payload


class BackendApiTests(unittest.TestCase):
    def test_health_endpoint(self):
        route = next(route for route in app.routes if route.path == "/")

        self.assertIn("GET", route.methods)
        self.assertEqual(
            health_check(),
            {"message": "MAMT2 Cloud SHM API is running"},
        )

    def test_metrics_endpoint(self):
        route = next(
            route for route in app.routes if route.path == "/metrics"
        )
        response = metrics()
        body = response.body.decode()

        self.assertIn("GET", route.methods)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.media_type.startswith("text/plain"))
        self.assertIn(
            "structvision_backend_http_requests_total",
            body,
        )
        self.assertIn(
            "structvision_backend_worker_calls_total",
            body,
        )


class BackendWorkerClientTests(unittest.TestCase):
    def test_mocked_worker_file_success(self):
        payload = {
            "status": "success",
            "boxes": [[1, 2, 3, 4]],
            "labels": ["spalling"],
            "scores": [0.95],
            "masks": [],
            "result_filename": "result.jpg",
            "result_image_base64": base64.b64encode(b"result-image").decode(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "input.jpg"
            image_path.write_bytes(b"input-image")

            with (
                patch.object(infer_mamt2, "OUTPUT_DIR", temp_path / "outputs"),
                patch.object(
                    infer_mamt2.requests,
                    "post",
                    return_value=FakeWorkerResponse(200, payload),
                ) as mocked_post,
            ):
                result = infer_mamt2.predict_image_via_worker_file(
                    str(image_path)
                )

            self.assertEqual(result["boxes"], payload["boxes"])
            self.assertEqual(result["result_filename"], "result.jpg")
            self.assertEqual(
                Path(result["result_image_path"]).read_bytes(),
                b"result-image",
            )
            self.assertEqual(mocked_post.call_count, 1)
            self.assertEqual(
                mocked_post.call_args.args[0],
                "http://127.0.0.1:9000/predict-file",
            )
            self.assertEqual(
                mocked_post.call_args.kwargs["timeout"],
                infer_mamt2.WORKER_TIMEOUT_SECONDS,
            )

    def test_worker_timeout_is_reported_without_external_request(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "input.jpg"
            image_path.write_bytes(b"input-image")

            with patch.object(
                infer_mamt2.requests,
                "post",
                side_effect=requests.Timeout("simulated timeout"),
            ):
                with self.assertRaisesRegex(RuntimeError, "timed out after"):
                    infer_mamt2.predict_image_via_worker_file(str(image_path))

    def test_worker_error_response_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "input.jpg"
            image_path.write_bytes(b"input-image")

            with patch.object(
                infer_mamt2.requests,
                "post",
                return_value=FakeWorkerResponse(
                    503,
                    {"status": "error", "message": "worker unavailable"},
                ),
            ):
                with self.assertRaisesRegex(
                    infer_mamt2.WorkerInvalidResponseError,
                    "HTTP 503",
                ):
                    infer_mamt2.predict_image_via_worker_file(str(image_path))


if __name__ == "__main__":
    unittest.main()
