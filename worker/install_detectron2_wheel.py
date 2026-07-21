"""Download the pinned Detectron2 wheel and enforce its published SHA256."""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path


WHEEL_FILENAME = "detectron2-0.6-cp312-cp312-linux_x86_64.whl"
WHEEL_URL = (
    "https://github.com/DavidYz/mamt2-cloud-shm/releases/download/"
    "runtime-deps-v1/"
    f"{WHEEL_FILENAME}"
)
WHEEL_SHA256 = "eb7295b6cb477467cb03660ea024a11ab13e97fc12b157040b9234897f809ace"
DEFAULT_DESTINATION = Path("/tmp") / WHEEL_FILENAME


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_wheel(path: Path) -> None:
    actual = sha256_file(path)
    if actual != WHEEL_SHA256:
        raise RuntimeError(
            f"Detectron2 wheel SHA256 mismatch: expected={WHEEL_SHA256} actual={actual}"
        )


def download_wheel(destination: Path = DEFAULT_DESTINATION) -> Path:
    request = urllib.request.Request(
        WHEEL_URL,
        headers={"User-Agent": "StructVision-worker-build/runtime-deps-v1"},
    )
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        verify_wheel(partial)
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return destination


if __name__ == "__main__":
    wheel_path = download_wheel()
    print(f"verified Detectron2 wheel: {wheel_path} sha256={WHEEL_SHA256}")
