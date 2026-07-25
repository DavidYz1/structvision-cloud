from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app import infer_mamt2
from app import main as backend_main
from app.main import app, health_check, metrics


class BackendApiTests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def backend_client(self):
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://backend.test",
            ) as client:
                yield client

    async def test_existing_root_health_endpoint(self):
        route = next(route for route in app.routes if route.path == "/")

        self.assertIn("GET", route.methods)
        self.assertEqual(
            health_check(),
            {"message": "MAMT2 Cloud SHM API is running"},
        )

    async def test_liveness_endpoint(self):
        async with self.backend_client() as client:
            response = await client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})

    async def test_readiness_endpoint(self):
        async with self.backend_client() as client:
            response = await client.get("/readyz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})

    async def test_predict_preserves_response_contract(self):
        worker_result = {
            "boxes": [[1, 2, 3, 4]],
            "labels": ["spalling"],
            "scores": [0.95],
            "masks": [],
            "result_image_path": "/outputs/result.jpg",
            "result_filename": "result.jpg",
        }
        predict_mock = AsyncMock(return_value=worker_result)

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(backend_main, "UPLOAD_DIR", Path(temp_dir)),
                patch.object(
                    backend_main,
                    "predict_image",
                    predict_mock,
                ),
            ):
                async with self.backend_client() as client:
                    response = await client.post(
                        "/predict",
                        files={
                            "file": (
                                "input.jpg",
                                b"input-image",
                                "image/jpeg",
                            )
                        },
                    )
                    worker_client = app.state.worker_client

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["content-type"].startswith("application/json")
        )
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["input_filename"].endswith(".jpg"))
        self.assertEqual(payload["boxes"], worker_result["boxes"])
        self.assertEqual(payload["labels"], worker_result["labels"])
        self.assertEqual(payload["scores"], worker_result["scores"])
        self.assertEqual(payload["masks"], worker_result["masks"])
        self.assertEqual(
            payload["result_image_path"],
            worker_result["result_image_path"],
        )
        self.assertEqual(payload["result_filename"], "result.jpg")
        self.assertEqual(payload["result_url"], "/results/result.jpg")
        self.assertEqual(
            payload["result_image_url"],
            "/api/results/result.jpg",
        )
        predict_mock.assert_awaited_once()
        self.assertIs(predict_mock.await_args.args[1], worker_client)

    async def test_liveness_responds_while_prediction_is_waiting(self):
        prediction_started = asyncio.Event()
        finish_prediction = asyncio.Event()

        async def delayed_prediction(*_args):
            prediction_started.set()
            await finish_prediction.wait()
            return {
                "boxes": [],
                "labels": [],
                "scores": [],
                "masks": [],
                "result_image_path": "/outputs/result.jpg",
                "result_filename": "result.jpg",
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(backend_main, "UPLOAD_DIR", Path(temp_dir)),
                patch.object(
                    backend_main,
                    "predict_image",
                    side_effect=delayed_prediction,
                ),
            ):
                async with self.backend_client() as client:
                    predict_task = asyncio.create_task(
                        client.post(
                            "/predict",
                            files={
                                "file": (
                                    "input.jpg",
                                    b"input-image",
                                    "image/jpeg",
                                )
                            },
                        )
                    )
                    await asyncio.wait_for(
                        prediction_started.wait(),
                        timeout=1,
                    )
                    try:
                        health_response = await asyncio.wait_for(
                            client.get("/healthz"),
                            timeout=1,
                        )
                    finally:
                        finish_prediction.set()
                    predict_response = await asyncio.wait_for(
                        predict_task,
                        timeout=1,
                    )

        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(
            health_response.json(),
            {"status": "healthy"},
        )
        self.assertEqual(predict_response.status_code, 200)

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


class BackendWorkerClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_mocked_worker_file_success(self):
        payload = {
            "status": "success",
            "boxes": [[1, 2, 3, 4]],
            "labels": ["spalling"],
            "scores": [0.95],
            "masks": [],
            "result_filename": "result.jpg",
            "result_image_base64": base64.b64encode(b"result-image").decode(),
        }
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json=payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "input.jpg"
            image_path.write_bytes(b"input-image")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                with patch.object(
                    infer_mamt2,
                    "OUTPUT_DIR",
                    temp_path / "outputs",
                ):
                    result = await infer_mamt2.predict_image_via_worker_file(
                        str(image_path),
                        client,
                    )

            self.assertEqual(result["boxes"], payload["boxes"])
            self.assertEqual(result["result_filename"], "result.jpg")
            self.assertEqual(
                Path(result["result_image_path"]).read_bytes(),
                b"result-image",
            )
            self.assertEqual(len(requests_seen), 1)
            self.assertEqual(
                str(requests_seen[0].url),
                "http://127.0.0.1:9000/predict-file",
            )
            self.assertIn(
                "multipart/form-data",
                requests_seen[0].headers["content-type"],
            )
            self.assertIn(b'name="file"', requests_seen[0].content)
            self.assertEqual(
                requests_seen[0].extensions["timeout"]["read"],
                infer_mamt2.WORKER_TIMEOUT_SECONDS,
            )

    async def test_worker_timeout_is_reported_without_external_request(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout(
                "simulated timeout",
                request=request,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "input.jpg"
            image_path.write_bytes(b"input-image")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                with self.assertRaisesRegex(RuntimeError, "timed out after"):
                    await infer_mamt2.predict_image_via_worker_file(
                        str(image_path),
                        client,
                    )

    async def test_worker_connection_failure_is_reported(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(
                "simulated connection failure",
                request=request,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "input.jpg"
            image_path.write_bytes(b"input-image")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Failed to call MAMT2 Worker file endpoint",
                ):
                    await infer_mamt2.predict_image_via_worker_file(
                        str(image_path),
                        client,
                    )

    async def test_worker_error_response_is_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                503,
                json={
                    "status": "error",
                    "message": "worker unavailable",
                },
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "input.jpg"
            image_path.write_bytes(b"input-image")

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                with self.assertRaisesRegex(
                    infer_mamt2.WorkerInvalidResponseError,
                    "HTTP 503",
                ):
                    await infer_mamt2.predict_image_via_worker_file(
                        str(image_path),
                        client,
                    )


if __name__ == "__main__":
    unittest.main()
