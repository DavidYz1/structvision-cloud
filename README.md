# MAMT2 Cloud SHM

MAMT2 Cloud SHM is a cloud-native platform for structural surface damage detection and instance segmentation.

Current architecture:

```text
React frontend -> FastAPI backend api -> MAMT2 Worker -> Detectron2/MAMT2 model
```

## Services

- frontend: `http://localhost:5173`
- backend api: `http://127.0.0.1:8000`
- mamt2 worker: `http://127.0.0.1:9000`

The frontend does not need to distinguish mock mode from real mode. It always calls the backend api, and the backend decides whether to use mock inference or the real MAMT2 Worker.

## Mock Mode

Mock mode only starts the lightweight backend api. It does not require the MAMT2 Worker.

```bash
conda activate mamt2-api
bash scripts/start_backend_mock.sh
```

Then start the frontend:

```bash
cd frontend
npm run dev
```

## Real MAMT2 Mode

Start the real MAMT2 Worker first:

```bash
conda activate General
bash scripts/start_worker.sh
```

Start the backend api in real inference mode:

```bash
conda activate mamt2-api
bash scripts/start_backend_real.sh
```

Start the frontend:

```bash
cd frontend
npm run dev
```

## Model Files

The real model weights and config are still stored in the local `MAMT2-final` project during Windows development. In the Docker/K8s phase, these paths should be configured through environment variables and model volume mounts instead of hard-coded local paths.

Model weight files should not be committed to Git.

## Roadmap

1. Dockerize frontend and backend api.
2. Add Docker Compose for local multi-service startup.
3. Dockerize the MAMT2 Worker.
4. Deploy to Kubernetes.
5. Add Redis, MinIO, MySQL, Prometheus, and Grafana for production-grade task queueing, object storage, metadata persistence, monitoring, and visualization.

## Dependency Notes

- `backend/requirements.txt` contains only lightweight API dependencies for the FastAPI backend.
- `worker/requirements.txt` documents the heavier MAMT2 Worker dependencies.
- Windows local real inference currently uses the existing `General` conda environment.
- For Ubuntu/Docker, create a dedicated `mamt2-worker` environment from `worker/environment.yml` instead of reusing `General`.
- Do not commit a full `pip freeze` from `General`; it contains machine-specific and unrelated packages.
