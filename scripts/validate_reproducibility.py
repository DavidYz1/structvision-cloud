#!/usr/bin/env python3
"""Validate the repository's authoritative dependency and build inputs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
PIN_PATTERN = re.compile(
    r"(?P<name>[A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?"
    r"==(?P<version>[A-Za-z0-9_.+!-]+)"
)
FROM_PATTERN = re.compile(
    r"^FROM\s+(?P<image>\S+)(?:\s+AS\s+\S+)?$",
    re.IGNORECASE | re.MULTILINE,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Reproducibility validation failed: {message}")


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def exact_pins(path: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line_number, raw_line in enumerate(read(path).splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_PATTERN.fullmatch(line)
        require(
            match is not None,
            f"{path}:{line_number} must be an exact name==version pin",
        )
        name = normalize_package_name(match.group("name"))
        require(name not in pins, f"{path} contains duplicate package {name}")
        pins[name] = match.group("version")
    require(pins, f"{path} contains no dependency pins")
    return pins


def hashed_lock(path: str) -> dict[str, str]:
    text = read(path)
    lines = text.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if PIN_PATTERN.match(line)
    ]
    require(starts, f"{path} contains no exact package pins")

    pins: dict[str, str] = {}
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        match = PIN_PATTERN.match(lines[start])
        require(match is not None, f"{path}:{start + 1} has an invalid requirement")
        name = normalize_package_name(match.group("name"))
        require(name not in pins, f"{path} contains duplicate package {name}")
        pins[name] = match.group("version")
        block = "\n".join(lines[start:end])
        require(
            "--hash=sha256:" in block,
            f"{path} entry lacks a SHA256 hash: {lines[start]}",
        )
    return pins


def validate_python_dependencies() -> None:
    dependency_inputs = (
        "scripts/requirements-ci.in",
        "scripts/requirements-ci.txt",
        "backend/requirements.in",
        "backend/requirements.txt",
        "backend/requirements-test.txt",
        "worker/requirements-docker.in",
        "worker/base-packages-docker.txt",
        "worker/requirements-docker.txt",
    )
    banned_patterns = {
        "editable dependency": re.compile(
            r"^\s*(?:-e|--editable)(?:\s|=)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "file URL": re.compile(r"file://", re.IGNORECASE),
        "personal home path": re.compile(
            r"(?:/home/(?!worker(?:/|\b))[^/\s]+/|[A-Za-z]:[\\/](?:Users|home)[\\/])"
        ),
        "Conda environment path": re.compile(
            r"(?:/opt/conda/envs/|[\\/](?:anaconda|anaconda3|miniconda|miniconda3)[\\/]envs[\\/])",
            re.IGNORECASE,
        ),
    }
    for path in dependency_inputs:
        text = read(path)
        for description, pattern in banned_patterns.items():
            require(
                pattern.search(text) is None,
                f"{path} contains a {description}",
            )

    require(
        not (REPO_ROOT / "worker/current-environment-freeze.txt").exists(),
        "non-authoritative current-environment-freeze.txt must stay removed",
    )

    ci_direct = exact_pins("scripts/requirements-ci.in")
    ci_lock = hashed_lock("scripts/requirements-ci.txt")
    require(
        ci_lock == ci_direct,
        "CI tool lock must exactly match its direct dependency input",
    )

    backend_direct = exact_pins("backend/requirements.in")
    backend_lock = hashed_lock("backend/requirements.txt")
    for package, version in backend_direct.items():
        require(
            backend_lock.get(package) == version,
            f"Backend direct pin {package}=={version} is absent from the lock",
        )

    test_lines = [
        line.strip()
        for line in read("backend/requirements-test.txt").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    require(
        test_lines == ["-r requirements.txt"],
        "Backend test input must include only the hashed runtime lock",
    )

    worker_direct = exact_pins("worker/requirements-docker.in")
    worker_base = exact_pins("worker/base-packages-docker.txt")
    worker_lock = hashed_lock("worker/requirements-docker.txt")
    require(
        worker_base.keys().isdisjoint(worker_lock),
        "Worker base and install locks must not contain the same package",
    )
    for package, version in worker_direct.items():
        actual = worker_lock.get(package, worker_base.get(package))
        require(
            actual == version,
            f"Worker direct pin {package}=={version} is absent from the base or install lock",
        )
    require(
        worker_direct.get("prometheus-client") == "0.25.0",
        "Worker prometheus-client must remain pinned to the audited image version",
    )


def validate_frontend_lock() -> None:
    package = json.loads(read("frontend/package.json"))
    lock = json.loads(read("frontend/package-lock.json"))
    require(lock.get("lockfileVersion") == 3, "npm lockfileVersion must be 3")

    root = lock.get("packages", {}).get("")
    require(isinstance(root, dict), "npm lock must contain the root package")
    for key in ("dependencies", "devDependencies"):
        require(
            root.get(key, {}) == package.get(key, {}),
            f"package-lock root {key} differs from package.json",
        )

    for path, metadata in lock["packages"].items():
        if not path:
            continue
        version = metadata.get("version")
        integrity = metadata.get("integrity", "")
        require(version and version != "latest", f"{path} lacks an exact version")
        require(
            integrity.startswith(("sha512-", "sha256-")),
            f"{path} lacks npm integrity metadata",
        )

    require(read("frontend/.node-version").strip() == "20.20.2", "Node version drifted")
    require("RUN npm ci" in read("frontend/Dockerfile"), "Frontend image must use npm ci")
    require(
        "run: npm ci" in read(".github/workflows/ci.yml"),
        "Frontend CI must use npm ci",
    )


def validate_base_images() -> None:
    dockerfiles = (
        "frontend/Dockerfile",
        "backend/Dockerfile",
        "worker/Dockerfile",
        "worker/Dockerfile.hf",
    )
    for path in dockerfiles:
        dockerfile = read(path)
        images = FROM_PATTERN.findall(dockerfile)
        require(images, f"{path} contains no FROM image")
        for image in images:
            require(":latest" not in image.lower(), f"{path} uses a latest image")
            require(
                re.fullmatch(r".+:[^@]+@sha256:[0-9a-f]{64}", image) is not None,
                f"{path} base image must retain a tag and pin a SHA256 digest",
            )
        if path.startswith("worker/"):
            require(
                "--require-hashes" in dockerfile,
                f"{path} must verify Python distribution hashes",
            )
            require(
                "--no-deps" in dockerfile,
                f"{path} must not resolve unpinned transitive dependencies",
            )
            require(
                "--no-build-isolation" in dockerfile,
                f"{path} must not create a floating Python build environment",
            )
            require(
                "validate_base_packages.py /tmp/base-packages-docker.txt" in dockerfile,
                f"{path} must validate packages inherited from its base image",
            )

    workflow = read(".github/workflows/ci.yml")
    require("runs-on: ubuntu-latest" not in workflow, "CI runner label must not float")
    require(
        "--file worker/Dockerfile.hf" in workflow,
        "manual Worker build must use Dockerfile.hf",
    )
    require(
        re.search(r"--file\s+worker/Dockerfile(?:\s|$)", workflow) is None,
        "legacy Worker Dockerfile entered the CI build chain",
    )


def load_yaml(path: str) -> Any:
    return yaml.safe_load(read(path))


def find_resource(path: str, kind: str, name: str) -> dict[str, Any]:
    documents = [
        document
        for document in yaml.safe_load_all(read(path))
        if document
    ]
    matches = [
        document
        for document in documents
        if document.get("kind") == kind
        and document.get("metadata", {}).get("name") == name
    ]
    require(len(matches) == 1, f"{path} must contain one {kind}/{name}")
    return matches[0]


def validate_model_and_wheel_provenance() -> None:
    manifest = load_yaml("model/manifest.yaml")
    values = load_yaml("helm/values.yaml")
    worker = find_resource("k8s/worker.yaml", "Deployment", "mamt2-worker")
    pod_spec = worker["spec"]["template"]["spec"]
    downloader = next(
        container
        for container in pod_spec["initContainers"]
        if container["name"] == "model-weight-downloader"
    )
    downloader_env = {
        item["name"]: item["value"] for item in downloader.get("env", [])
    }

    model = manifest["model"]
    helm_model = values["worker"]["model"]
    require(
        COMMIT_PATTERN.fullmatch(model["revision"]) is not None,
        "Hugging Face model revision must be a full 40-character commit",
    )
    require(
        re.fullmatch(r"[0-9a-f]{64}", model["sha256"]) is not None,
        "Hugging Face model SHA256 must be fixed",
    )
    expected_url = (
        f"https://huggingface.co/{model['repository']}/resolve/"
        f"{model['revision']}/{model['filename']}?download=true"
    )
    require(helm_model["download"]["url"] == expected_url, "Helm model URL drifted")
    for manifest_key, helm_key, env_name in (
        ("repository", "repository", "MODEL_REPOSITORY"),
        ("revision", "revision", "MODEL_REVISION"),
        ("filename", "filename", "MODEL_FILENAME"),
        ("sha256", "sha256", "MODEL_SHA256"),
    ):
        expected = model[manifest_key]
        require(helm_model[helm_key] == expected, f"Helm model {helm_key} drifted")
        require(downloader_env[env_name] == expected, f"raw {env_name} drifted")
    require(downloader_env["MODEL_URL"] == expected_url, "raw MODEL_URL drifted")

    downloader_image = helm_model["download"]["image"]
    digest = downloader_image["digest"]
    require(
        SHA256_PATTERN.fullmatch(digest) is not None,
        "downloader image digest must be a SHA256",
    )
    require(
        downloader_image["tag"] != "latest",
        "downloader image tag must not be latest",
    )
    expected_downloader_image = (
        f"{downloader_image['repository']}:{downloader_image['tag']}@{digest}"
    )
    require(
        downloader["image"] == expected_downloader_image,
        "raw downloader image differs from Helm tag+digest",
    )

    source = manifest["detectron2"]["source"]
    require(
        source["repository"]
        == "https://github.com/facebookresearch/detectron2.git",
        "Detectron2 source repository drifted",
    )
    require(
        COMMIT_PATTERN.fullmatch(source["revision"]) is not None,
        "Detectron2 source revision must be a full commit",
    )
    patch_path = REPO_ROOT / source["patch"]["path"]
    require(patch_path.is_file(), "Detectron2 source patch is missing")
    require(
        sha256_file(patch_path) == source["patch"]["sha256"],
        "Detectron2 source patch SHA256 mismatch",
    )

    install_spec = importlib.util.spec_from_file_location(
        "install_detectron2_wheel",
        REPO_ROOT / "worker/install_detectron2_wheel.py",
    )
    require(install_spec is not None and install_spec.loader is not None, "wheel installer")
    installer = importlib.util.module_from_spec(install_spec)
    install_spec.loader.exec_module(installer)

    wheel = manifest["detectron2"]["wheel"]
    require(wheel["filename"] == installer.WHEEL_FILENAME, "wheel filename drifted")
    require(wheel["url"] == installer.WHEEL_URL, "wheel URL drifted")
    require(wheel["sha256"] == installer.WHEEL_SHA256, "wheel SHA256 drifted")
    require(
        wheel["url"].startswith("https://github.com/")
        and "/releases/download/runtime-deps-v1/" in wheel["url"],
        "wheel URL must use the versioned runtime-deps-v1 release",
    )
    require(
        re.fullmatch(r"[0-9a-f]{64}", wheel["sha256"]) is not None,
        "wheel SHA256 must be fixed",
    )


def validate_docker_contexts() -> None:
    allowlists = {
        ".dockerignore": {
            "!worker/Dockerfile.hf",
            "!worker/base-packages-docker.txt",
            "!worker/requirements-docker.txt",
            "!worker/validate_base_packages.py",
            "!worker/install_detectron2_wheel.py",
            "!model/manifest.yaml",
        },
        "frontend/.dockerignore": {
            "!Dockerfile",
            "!package.json",
            "!package-lock.json",
            "!src/**",
            "!public/**",
        },
        "backend/.dockerignore": {
            "!Dockerfile",
            "!requirements.txt",
            "!app/*.py",
        },
    }
    weight_suffixes = (".pth", ".pt", ".ckpt", ".onnx", ".safetensors")
    for path, required_entries in allowlists.items():
        lines = read(path).splitlines()
        require(lines and lines[0] == "**", f"{path} must be deny-by-default")
        entries = set(lines)
        require(
            required_entries <= entries,
            f"{path} is missing required allowlist entries",
        )
        for line in lines:
            if line.startswith("!"):
                require(
                    not line.lower().endswith(weight_suffixes),
                    f"{path} allowlists a model weight",
                )

    require(
        "!worker/current-environment-freeze.txt" not in read(".dockerignore"),
        "historical environment snapshot entered the Worker build context",
    )


def main() -> None:
    validate_python_dependencies()
    validate_frontend_lock()
    validate_base_images()
    validate_model_and_wheel_provenance()
    validate_docker_contexts()
    print(
        "Reproducibility validation passed: dependency locks, immutable images, "
        "artifact provenance, and Docker context allowlists"
    )


if __name__ == "__main__":
    main()
