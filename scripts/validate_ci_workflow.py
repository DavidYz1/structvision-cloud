#!/usr/bin/env python3
"""Perform lightweight structural checks on the repository CI workflow."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


EXPRESSION_PATTERN = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
ALLOWED_EXPRESSION_CONTEXTS = ("github.", "inputs.", "matrix.")
ACTION_REFERENCE_PATTERN = re.compile(
    r"^\s*uses:\s*[^@\s]+@(?P<revision>[^\s#]+)",
    re.MULTILINE,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"CI workflow validation failed: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    text = args.workflow.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)

    require(isinstance(workflow, dict), "workflow root must be a mapping")
    require(
        workflow.get("permissions") == {"contents": "read"},
        "permissions must only grant contents: read",
    )

    triggers = workflow.get("on")
    require(isinstance(triggers, dict), "on must be a trigger mapping")
    require(
        set(triggers) == {"pull_request", "push", "workflow_dispatch"},
        "triggers must be pull_request, push, and workflow_dispatch",
    )
    require(
        triggers["push"] == {"branches": ["main"]},
        "push must be limited to main",
    )
    workflow_dispatch = triggers["workflow_dispatch"]
    require(
        workflow_dispatch
        == {
            "inputs": {
                "build_worker": {
                    "description": (
                        "Build the large Worker image without pushing"
                    ),
                    "required": "false",
                    "default": "false",
                    "type": "boolean",
                }
            }
        },
        "workflow_dispatch must expose a default-off build_worker input",
    )

    concurrency = workflow.get("concurrency")
    require(isinstance(concurrency, dict), "concurrency must be configured")
    require(
        concurrency.get("cancel-in-progress") == "true",
        "concurrency.cancel-in-progress must be true",
    )
    require(
        "github.workflow" in concurrency.get("group", "")
        and "github.ref" in concurrency.get("group", ""),
        "concurrency group must scope runs by workflow and ref",
    )

    jobs = workflow.get("jobs")
    require(isinstance(jobs, dict) and jobs, "at least one job is required")
    for job_name, job in jobs.items():
        require(
            isinstance(job, dict) and "timeout-minutes" in job,
            f"job {job_name} must set timeout-minutes",
        )
        require(
            job.get("runs-on") == "ubuntu-24.04",
            f"job {job_name} must use the fixed ubuntu-24.04 runner label",
        )
        timeout = int(job["timeout-minutes"])
        require(1 <= timeout <= 60, f"job {job_name} timeout is unreasonable")

        needs = job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        for dependency in needs:
            require(
                dependency in jobs,
                f"job {job_name} needs unknown job {dependency}",
            )

    require("packages:" not in text, "packages permission must not be present")
    require("secrets." not in text, "workflow must not reference secrets")
    require("github.token" not in text, "workflow must not reference github.token")
    require(
        "python scripts/validate_reproducibility.py" in text,
        "reproducible build input validation must run in CI",
    )
    require(
        "python scripts/validate_publish_workflow.py" in text
        and ".github/workflows/publish-images.yml" in text,
        "GHCR publication workflow validation must run in CI",
    )
    require(
        "pip install --require-hashes -r backend/requirements-test.txt" in text,
        "Backend CI must enforce hashes from the dependency lock",
    )
    require(
        text.count(
            "pip install --require-hashes -r scripts/requirements-ci.txt"
        )
        == 2,
        "quality and Worker layout jobs must use the hashed CI tool lock",
    )

    action_revisions = ACTION_REFERENCE_PATTERN.findall(text)
    require(action_revisions, "workflow must use external actions")
    for revision in action_revisions:
        require(
            re.fullmatch(r"[0-9a-f]{40}", revision) is not None,
            f"action reference must use a full commit SHA: {revision}",
        )

    worker_image = jobs.get("worker-image")
    require(worker_image is not None, "manual Worker image job is required")
    require(
        worker_image.get("if")
        == "${{ github.event_name == 'workflow_dispatch' && inputs.build_worker }}",
        "Worker image job must only run after explicit manual opt-in",
    )

    require(
        text.count("${{") == text.count("}}"),
        "GitHub expression delimiters are unbalanced",
    )
    expressions = EXPRESSION_PATTERN.findall(text)
    require(expressions, "expected at least one GitHub expression")
    for expression in expressions:
        expression = expression.strip()
        require(expression, "empty GitHub expression")
        require(
            any(context in expression for context in ALLOWED_EXPRESSION_CONTEXTS),
            f"unexpected expression context: {expression}",
        )

    print(
        f"CI workflow validation passed: {len(jobs)} jobs, "
        f"{len(expressions)} expressions"
    )


if __name__ == "__main__":
    main()
