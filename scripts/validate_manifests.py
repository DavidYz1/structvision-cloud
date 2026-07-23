#!/usr/bin/env python3
"""Compare Helm render variants with the raw Kubernetes manifests."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


PROXY_ENV_NAMES = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Manifest validation failed: {message}")


def load_yaml_file(path: Path) -> list[dict[str, Any]]:
    documents = [
        document
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if document
    ]
    require(documents, f"{path} contains no YAML documents")
    return documents


def load_yaml_directory(directory: Path) -> list[dict[str, Any]]:
    paths = sorted(directory.glob("*.yaml"))
    require(paths, f"{directory} contains no YAML files")
    return [document for path in paths for document in load_yaml_file(path)]


def resource_index(
    documents: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for document in documents:
        key = (document["kind"], document["metadata"]["name"])
        require(key not in result, f"duplicate resource {key[0]}/{key[1]}")
        result[key] = document
    return result


def normalize_resource(resource: dict[str, Any]) -> dict[str, Any]:
    resource = deepcopy(resource)

    if resource["kind"] == "PersistentVolumeClaim":
        resource["metadata"].pop("labels", None)

    if resource["kind"] == "Deployment":
        annotations = resource["spec"]["template"]["metadata"].get(
            "annotations", {}
        )
        annotations.pop("checksum/config", None)
        if not annotations:
            resource["spec"]["template"]["metadata"].pop(
                "annotations", None
            )

        strategy = resource["spec"].get("strategy")
        if strategy and strategy.get("rollingUpdate") is None:
            strategy.pop("rollingUpdate", None)

    return resource


def container_env_locations(
    deployment: dict[str, Any],
) -> dict[str, set[tuple[str, str]]]:
    locations: dict[str, set[tuple[str, str]]] = {}
    pod_spec = deployment["spec"]["template"]["spec"]
    for container_group in ("initContainers", "containers"):
        for container in pod_spec.get(container_group, []):
            for env in container.get("env", []):
                locations.setdefault(env["name"], set()).add(
                    (container_group, container["name"])
                )
    return locations


def validate_observability(
    default: dict[tuple[str, str], dict[str, Any]],
    service_monitor_disabled: dict[tuple[str, str], dict[str, Any]],
    dashboard_disabled: dict[tuple[str, str], dict[str, Any]],
) -> None:
    default_service_monitors = [
        key for key in default if key[0] == "ServiceMonitor"
    ]
    require(
        len(default_service_monitors) == 2,
        "default render must contain two ServiceMonitors",
    )
    require(
        ("ConfigMap", "structvision-grafana-dashboard") in default,
        "default render must contain the Grafana Dashboard ConfigMap",
    )
    require(
        not any(key[0] == "ServiceMonitor" for key in service_monitor_disabled),
        "ServiceMonitor disable switch still rendered a ServiceMonitor",
    )
    require(
        ("ConfigMap", "structvision-grafana-dashboard")
        in service_monitor_disabled,
        "ServiceMonitor switch unexpectedly disabled the dashboard",
    )
    require(
        ("ConfigMap", "structvision-grafana-dashboard")
        not in dashboard_disabled,
        "dashboard disable switch still rendered the dashboard",
    )
    require(
        len([key for key in dashboard_disabled if key[0] == "ServiceMonitor"])
        == 2,
        "dashboard switch unexpectedly disabled ServiceMonitors",
    )


def validate_proxy(
    default: dict[tuple[str, str], dict[str, Any]],
    proxy_enabled: dict[tuple[str, str], dict[str, Any]],
) -> None:
    worker_key = ("Deployment", "mamt2-worker")
    default_locations = container_env_locations(default[worker_key])
    require(
        PROXY_ENV_NAMES.isdisjoint(default_locations),
        "default Worker render contains proxy variables",
    )

    enabled_locations = container_env_locations(proxy_enabled[worker_key])
    for name in PROXY_ENV_NAMES:
        require(
            enabled_locations.get(name)
            == {("initContainers", "model-weight-downloader")},
            f"{name} must only be set on model-weight-downloader",
        )


def validate_raw_alignment(
    helm: dict[tuple[str, str], dict[str, Any]],
) -> None:
    core_documents = load_yaml_directory(Path("k8s"))
    optional_documents = load_yaml_directory(Path("k8s/optional"))
    raw = resource_index(core_documents + optional_documents)

    expected_core = {
        ("Namespace", "mamt2"),
        ("ConfigMap", "mamt2-config"),
        ("Deployment", "frontend"),
        ("Service", "frontend"),
        ("Deployment", "backend"),
        ("Service", "backend"),
        ("PersistentVolumeClaim", "mamt2-model"),
        ("Deployment", "mamt2-worker"),
        ("Service", "mamt2-worker"),
    }
    core_keys = set(resource_index(core_documents))
    require(core_keys == expected_core, "unexpected raw core resource set")

    expected_optional = {
        ("Ingress", "mamt2-ingress"),
        ("ServiceMonitor", "backend"),
        ("ServiceMonitor", "mamt2-worker"),
    }
    optional_keys = set(resource_index(optional_documents))
    require(
        optional_keys == expected_optional,
        "unexpected raw optional resource set",
    )

    comparable_keys = (
        expected_core - {("Namespace", "mamt2")}
    ) | expected_optional
    for key in sorted(comparable_keys):
        require(key in helm, f"Helm render is missing {key[0]}/{key[1]}")
        require(
            normalize_resource(helm[key]) == normalize_resource(raw[key]),
            f"raw {key[0]}/{key[1]} differs from Helm default",
        )

    worker = raw[("Deployment", "mamt2-worker")]
    pod_spec = worker["spec"]["template"]["spec"]
    downloader = next(
        container
        for container in pod_spec["initContainers"]
        if container["name"] == "model-weight-downloader"
    )
    script = downloader["command"][2]
    for marker in (
        ".part.XXXXXX",
        "trap 'rm -f",
        "sha256sum -c",
        "curl \\",
        "--fail",
        "mv -f",
        "skipping download",
    ):
        require(marker in script, f"Worker downloader lacks {marker!r}")

    worker_container = next(
        container
        for container in pod_spec["containers"]
        if container["name"] == "worker"
    )
    model_mount = next(
        mount
        for mount in worker_container["volumeMounts"]
        if mount["name"] == "model-storage"
    )
    require(
        model_mount.get("readOnly") is True,
        "Worker model mount must be read-only",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--default", required=True, type=Path)
    parser.add_argument(
        "--service-monitor-disabled",
        required=True,
        type=Path,
    )
    parser.add_argument("--dashboard-disabled", required=True, type=Path)
    parser.add_argument("--proxy-enabled", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    default = resource_index(load_yaml_file(args.default))
    service_monitor_disabled = resource_index(
        load_yaml_file(args.service_monitor_disabled)
    )
    dashboard_disabled = resource_index(
        load_yaml_file(args.dashboard_disabled)
    )
    proxy_enabled = resource_index(load_yaml_file(args.proxy_enabled))

    validate_observability(
        default,
        service_monitor_disabled,
        dashboard_disabled,
    )
    validate_proxy(default, proxy_enabled)
    validate_raw_alignment(default)

    print(
        "Manifest validation passed: Helm switches, proxy isolation, "
        "raw core/optional YAML, and Worker downloader logic"
    )


if __name__ == "__main__":
    main()
