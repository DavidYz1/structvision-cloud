from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


REGISTRY = CollectorRegistry()

HTTP_REQUESTS_TOTAL = Counter(
    "structvision_backend_http_requests_total",
    "Total Backend HTTP requests.",
    ("method", "route", "status_code"),
    registry=REGISTRY,
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "structvision_backend_http_request_duration_seconds",
    "Backend HTTP request duration in seconds.",
    ("method", "route"),
    registry=REGISTRY,
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "structvision_backend_http_requests_in_progress",
    "Backend HTTP requests currently in progress.",
    ("method",),
    registry=REGISTRY,
)
WORKER_CALLS_TOTAL = Counter(
    "structvision_backend_worker_calls_total",
    "Total calls from the Backend to the GPU Worker.",
    ("endpoint", "result"),
    registry=REGISTRY,
)
WORKER_CALL_DURATION_SECONDS = Histogram(
    "structvision_backend_worker_call_duration_seconds",
    "Backend-to-Worker network call and response parsing duration in seconds.",
    ("endpoint",),
    registry=REGISTRY,
)
