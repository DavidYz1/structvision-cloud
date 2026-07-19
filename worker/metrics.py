from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


# A private registry keeps all application collectors centralized and also makes
# module reloads independent from collectors left in the process-wide registry.
REGISTRY = CollectorRegistry()

INFERENCE_REQUESTS_TOTAL = Counter(
    "structvision_worker_inference_requests_total",
    "Total Worker inference requests.",
    ("endpoint", "result"),
    registry=REGISTRY,
)
INFERENCE_DURATION_SECONDS = Histogram(
    "structvision_worker_inference_duration_seconds",
    "Worker prediction processing duration in seconds, excluding model loading.",
    ("endpoint",),
    registry=REGISTRY,
)
INFERENCE_IN_PROGRESS = Gauge(
    "structvision_worker_inference_in_progress",
    "Worker inference endpoint requests currently in progress.",
    ("endpoint",),
    registry=REGISTRY,
)
MODEL_LOAD_DURATION_SECONDS = Histogram(
    "structvision_worker_model_load_duration_seconds",
    "MAMT2 model load attempt duration in seconds.",
    registry=REGISTRY,
)
MODEL_LOADED = Gauge(
    "structvision_worker_model_loaded",
    "Whether the MAMT2 model is loaded successfully (1) or not (0).",
    registry=REGISTRY,
)
DETECTED_INSTANCES = Histogram(
    "structvision_worker_detected_instances",
    "Detected instance count produced by successful prediction processing.",
    ("endpoint",),
    buckets=(0, 1, 2, 3, 5, 10, 20, 50, 100, float("inf")),
    registry=REGISTRY,
)

MODEL_LOADED.set(0)
