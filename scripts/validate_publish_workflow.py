#!/usr/bin/env python3
"""Validate GHCR publication workflow structure and security boundaries."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION_REFERENCE_PATTERN = re.compile(
    r"^\s*uses:\s*(?P<action>[^@\s]+)@(?P<revision>[^\s#]+)",
    re.MULTILINE,
)
FULL_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
EXPECTED_ACTIONS = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
    "docker/setup-buildx-action": "4d04d5d9486b7bd6fa91e7baf45bbb4f8b9deedd",
    "docker/login-action": "b45d80f862d83dbcd57f89517bcf500b2ab88fb2",
    "docker/build-push-action": "f9f3042f7e2789586610d6e8b85c8f03e5195baf",
}
EXPECTED_IMAGES = [
    {
        "component": "Frontend",
        "image": "ghcr.io/davidyz1/structvision-frontend",
        "context": "frontend",
        "dockerfile": "frontend/Dockerfile",
        "description": "StructVision Cloud web frontend",
    },
    {
        "component": "Backend",
        "image": "ghcr.io/davidyz1/structvision-backend",
        "context": "backend",
        "dockerfile": "backend/Dockerfile",
        "description": "StructVision Cloud API backend",
    },
    {
        "component": "Worker",
        "image": "ghcr.io/davidyz1/structvision-worker",
        "context": ".",
        "dockerfile": "worker/Dockerfile.hf",
        "description": "StructVision Cloud GPU inference worker",
    },
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Publish workflow validation failed: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow", type=Path)
    return parser.parse_args()


def load_workflow(path: Path) -> tuple[str, dict[str, Any]]:
    require(path.is_file(), f"{path} does not exist")
    text = path.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    require(isinstance(workflow, dict), "workflow root must be a mapping")
    return text, workflow


def find_action_step(job: dict[str, Any], action: str) -> dict[str, Any]:
    matches = [
        step
        for step in job.get("steps", [])
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith(f"{action}@")
    ]
    require(len(matches) == 1, f"publish job must use {action} exactly once")
    return matches[0]


def validate_triggers_and_permissions(
    text: str,
    workflow: dict[str, Any],
) -> dict[str, Any]:
    triggers = workflow.get("on")
    require(
        triggers
        == {
            "workflow_dispatch": "",
            "push": {"tags": ["v[0-9]+.[0-9]+.[0-9]+"]},
        },
        "triggers must be only workflow_dispatch and semantic version tags",
    )
    require("pull_request" not in triggers, "pull_request must not publish")
    require(
        "branches" not in triggers["push"],
        "ordinary branch pushes must not publish",
    )
    require("inputs." not in text, "users must not supply image tags")
    require(
        workflow.get("permissions") == {"contents": "read"},
        "default permissions must contain only contents: read",
    )

    jobs = workflow.get("jobs")
    require(
        isinstance(jobs, dict)
        and set(jobs) == {"validate_source", "publish"},
        "workflow must contain only validate_source and publish jobs",
    )
    for job_name, job in jobs.items():
        require(
            job.get("runs-on") == "ubuntu-24.04",
            f"{job_name} must use ubuntu-24.04",
        )
        require("timeout-minutes" in job, f"{job_name} must have a timeout")
        permissions = job.get("permissions")
        if job_name == "publish":
            require(
                permissions == {"contents": "read", "packages": "write"},
                "only publish may add packages: write",
            )
        else:
            require(
                permissions in (None, {"contents": "read"}),
                f"{job_name} must not gain write permissions",
            )

    require(
        text.count("packages: write") == 1,
        "packages: write must appear exactly once",
    )
    return jobs


def validate_source_guard(text: str, job: dict[str, Any]) -> None:
    checkout = find_action_step(job, "actions/checkout")
    require(
        checkout.get("with") == {"fetch-depth": "0"},
        "source guard must fetch complete history for the main ancestry check",
    )
    require(
        job.get("outputs")
        == {
            "commit": "${{ steps.source.outputs.commit }}",
            "sha_tag": "${{ steps.source.outputs.sha_tag }}",
            "version": "${{ steps.source.outputs.version }}",
            "version_tag": "${{ steps.source.outputs.version_tag }}",
        },
        "source guard outputs must expose only validated refs",
    )
    required_fragments = (
        'GITHUB_REF}" != "refs/heads/main',
        r"^v[0-9]+\.[0-9]+\.[0-9]+$",
        "git merge-base --is-ancestor",
        "refs/remotes/origin/main",
        'sha_tag="sha-${commit}"',
    )
    for fragment in required_fragments:
        require(fragment in text, f"source guard is missing: {fragment}")


def validate_actions(text: str) -> None:
    action_references = ACTION_REFERENCE_PATTERN.findall(text)
    require(action_references, "workflow must use pinned external actions")
    found_actions: set[str] = set()
    for action, revision in action_references:
        require(
            FULL_SHA_PATTERN.fullmatch(revision) is not None,
            f"{action} must use a full commit SHA",
        )
        require(action in EXPECTED_ACTIONS, f"unexpected external action: {action}")
        require(
            revision == EXPECTED_ACTIONS[action],
            f"{action} revision differs from the audited release",
        )
        found_actions.add(action)
    require(
        found_actions == set(EXPECTED_ACTIONS),
        "required checkout, login, Buildx, and build-push actions are incomplete",
    )


def validate_publish_job(text: str, job: dict[str, Any]) -> None:
    require(job.get("needs") == "validate_source", "publish must need source guard")
    strategy = job.get("strategy")
    require(isinstance(strategy, dict), "publish strategy must be a mapping")
    require(strategy.get("fail-fast") == "false", "matrix fail-fast must be false")
    matrix = strategy.get("matrix")
    require(isinstance(matrix, dict), "publish matrix is missing")
    include = matrix.get("include")
    require(include == EXPECTED_IMAGES, "publish matrix entries drifted")
    for entry in include:
        require(
            entry["image"] == entry["image"].lower(),
            f"image name must be lowercase: {entry['image']}",
        )
        context_path = (
            REPO_ROOT
            if entry["context"] == "."
            else REPO_ROOT / entry["context"]
        )
        require(context_path.is_dir(), f"build context is missing: {entry['context']}")
        require(
            (REPO_ROOT / entry["dockerfile"]).is_file(),
            f"Dockerfile is missing: {entry['dockerfile']}",
        )

    checkout = find_action_step(job, "actions/checkout")
    require(
        checkout.get("with")
        == {"ref": "${{ needs.validate_source.outputs.commit }}"},
        "publish must check out the commit approved by the source guard",
    )
    find_action_step(job, "docker/setup-buildx-action")
    login = find_action_step(job, "docker/login-action")
    require(
        login.get("with")
        == {
            "registry": "ghcr.io",
            "username": "${{ github.actor }}",
            "password": "${{ secrets.GITHUB_TOKEN }}",
        },
        "GHCR login must use github.actor and secrets.GITHUB_TOKEN",
    )
    secret_names = re.findall(r"secrets\.([A-Za-z0-9_]+)", text)
    require(
        secret_names == ["GITHUB_TOKEN"],
        "GITHUB_TOKEN must be the only referenced secret",
    )
    require(
        re.search(r"\bPAT\b|personal access token", text, re.IGNORECASE) is None,
        "workflow must not use a PAT",
    )

    build = find_action_step(job, "docker/build-push-action")
    build_inputs = build.get("with")
    require(isinstance(build_inputs, dict), "build-push inputs must be a mapping")
    require(
        build_inputs.get("context") == "${{ matrix.context }}"
        and build_inputs.get("file") == "${{ matrix.dockerfile }}",
        "build must use matrix context and Dockerfile",
    )
    require(
        build_inputs.get("platforms") == "linux/amd64",
        "platform must be linux/amd64",
    )
    require(build_inputs.get("push") == "true", "build must publish its image")
    require(
        build_inputs.get("provenance") == "false"
        and build_inputs.get("sbom") == "false",
        "attestation and SBOM must remain out of scope",
    )
    labels = build_inputs.get("labels", "")
    for label in (
        "org.opencontainers.image.source=",
        "org.opencontainers.image.revision=",
        "org.opencontainers.image.version=",
        "org.opencontainers.image.description=",
    ):
        require(label in labels, f"OCI label is missing: {label}")

    require("latest" not in text.lower(), "workflow must never publish latest")
    require(
        "${IMAGE}:${VERSION_TAG}" in text
        and "${IMAGE}:${SHA_TAG}" in text,
        "version and full-commit tags are not prepared correctly",
    )
    require(
        "${{ steps.publish.outputs.digest }}" in text,
        "build-push digest output must be consumed",
    )
    require(
        "sha256:[0-9a-f]{64}" in text,
        "registry digest format must be validated",
    )
    require(
        'docker buildx imagetools inspect "${IMAGE}@${DIGEST}"' in text,
        "published image must be inspected by registry digest",
    )
    require(
        "GITHUB_STEP_SUMMARY" in text
        and "Registry digest" in text
        and "immutable image content identifier" in text,
        "job summary must explain tags and immutable digest",
    )
    require(
        re.search(r"\b(?:kubectl|helm|minikube)\b", text, re.IGNORECASE) is None,
        "publication workflow must not operate a cluster",
    )


def validate_regular_ci() -> None:
    ci_path = REPO_ROOT / ".github/workflows/ci.yml"
    ci_text, ci_workflow = load_workflow(ci_path)
    require(
        ci_workflow.get("permissions") == {"contents": "read"},
        "ci.yml default permissions must remain contents: read",
    )
    require(
        "packages:" not in ci_text,
        "ci.yml must not gain package permissions",
    )
    require(
        re.search(
            r"python\s+scripts/validate_publish_workflow\.py\s+"
            r"\\?\s*\.github/workflows/publish-images\.yml",
            ci_text,
        )
        is not None,
        "regular CI must validate the publication workflow",
    )


def main() -> None:
    args = parse_args()
    text, workflow = load_workflow(args.workflow)
    jobs = validate_triggers_and_permissions(text, workflow)
    validate_source_guard(text, jobs["validate_source"])
    validate_actions(text)
    validate_publish_job(text, jobs["publish"])
    validate_regular_ci()
    require(
        text.count("${{") == text.count("}}"),
        "GitHub expression delimiters are unbalanced",
    )
    print(
        "Publish workflow validation passed: main/tag guards, least privilege, "
        "3 amd64 GHCR images, OCI labels, and digest verification"
    )


if __name__ == "__main__":
    main()
