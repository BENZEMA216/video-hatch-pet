#!/usr/bin/env python3
"""Record a selected imagegen output in a video-hatch-pet run."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--source", required=True, help="Selected original imagegen output")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"source image not found: {source}")

    manifest_path = run_dir / "imagegen-jobs.json"
    manifest = load_json(manifest_path)
    jobs = manifest.get("jobs", [])
    job = next((item for item in jobs if item.get("id") == args.job_id), None)
    if not job:
        raise SystemExit(f"unknown job id: {args.job_id}")

    decoded = Path(job["decoded_path"]).expanduser()
    if not decoded.is_absolute():
        decoded = run_dir / decoded
    if decoded.exists() and not args.force:
        raise SystemExit(f"{decoded} already exists; pass --force to overwrite")
    decoded.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, decoded)

    if job.get("id") == "base":
        canonical = run_dir / "references" / "canonical-base.png"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, canonical)
        job["canonical_base"] = str(canonical)

    job["status"] = "complete"
    job["source_image"] = str(source)
    job["recorded_path"] = str(decoded)
    job["recorded_at"] = iso_now()
    write_json(manifest_path, manifest)

    print(json.dumps({"ok": True, "job_id": args.job_id, "recorded_path": str(decoded)}, indent=2))


if __name__ == "__main__":
    main()
