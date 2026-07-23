"""Verify packages inherited from the pinned Worker base image."""

from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("requirements", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mismatches: list[str] = []
    for raw_line in args.requirements.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, expected = line.split("==", 1)
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            mismatches.append(f"{name}: missing (expected {expected})")
            continue
        if actual != expected:
            mismatches.append(f"{name}: {actual} (expected {expected})")

    if mismatches:
        raise SystemExit(
            "Worker base package validation failed:\n- "
            + "\n- ".join(mismatches)
        )
    print("Worker base package versions match the pinned image")


if __name__ == "__main__":
    main()
