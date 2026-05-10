#!/usr/bin/env python3
"""Prepare a video-to-Codex-pet run directory."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

STATES = [
    ("idle", "calm breathing loop with a tiny blink or bob"),
    ("waving", "friendly paw or hand wave; no wave marks or motion arcs"),
    ("jumping", "vertical bounce using body position only; no shadows or dust"),
    ("failed", "small disappointed or dizzy reaction; attached effects only if needed"),
    ("review", "focused inspecting posture; no UI, code, paper, or text"),
    ("running", "busy in-place task loop; not literal directional travel"),
    ("running-right", "directional movement to the right; no speed lines or dust"),
    ("running-left", "directional movement to the left; no speed lines or dust"),
    ("celebrate", "small success loop; no detached floating symbols"),
]


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser().resolve()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-") or "video-pet"


def title_from_slug(value: str) -> str:
    return " ".join(part.capitalize() for part in slugify(value).split("-"))


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_json(command: list[str]) -> dict:
    proc = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def ffprobe(video: Path) -> dict:
    if not shutil.which("ffprobe"):
        raise SystemExit("ffprobe is required but was not found on PATH")
    return run_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video),
        ]
    )


def duration_seconds(metadata: dict) -> float:
    raw = metadata.get("format", {}).get("duration")
    if raw:
        return float(raw)
    for stream in metadata.get("streams", []):
        if stream.get("codec_type") == "video" and stream.get("duration"):
            return float(stream["duration"])
    raise SystemExit("could not determine video duration with ffprobe")


def extract_frame(video: Path, timestamp: float, out_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required but was not found on PATH")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out_path),
        ],
        check=True,
    )


def create_contact_sheet(frames: list[dict], output: Path, columns: int = 4) -> None:
    if not frames:
        raise SystemExit("no frames available for contact sheet")
    cell_w, cell_h = 260, 190
    label_h = 24
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows * (cell_h + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    for item in frames:
        index = item["index"]
        with Image.open(item["path"]) as im:
            im = im.convert("RGB")
            im.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
            x = (index % columns) * cell_w + (cell_w - im.width) // 2
            y = (index // columns) * (cell_h + label_h) + (cell_h - im.height) // 2
            sheet.paste(im, (x, y))
        label = f"{index:02d}  {item['timestamp']:.2f}s"
        lx = (index % columns) * cell_w + 8
        ly = (index // columns) * (cell_h + label_h) + cell_h + 4
        draw.text((lx, ly), label, fill=(20, 20, 20))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)


def base_prompt(pet_name: str, description: str, notes: str, style_notes: str) -> str:
    return f"""Create the canonical base art for a Codex App animated pet named {pet_name}.

Source: use the provided video contact sheet and selected video frames as identity and motion references.
Description: {description}
Pet notes: {notes or "infer the pet identity from the video references"}
Style notes: {style_notes or "compact pixel-art-adjacent chibi digital pet, thick dark outline, simple palette, flat cel shading"}

Output requirements:
- one complete full-body pet, centered, generous padding
- compact readable silhouette suitable for 192x208 sprite cells
- preserve the video's recognizable subject, colors, markings, and personality
- perfectly flat solid #00ff00 chroma-key background
- do not use #00ff00 inside the pet
- no text, labels, UI, scenery, floor, cast shadow, glow, or detached effects
"""


def row_prompt(
    pet_name: str,
    state: str,
    action: str,
    description: str,
    notes: str,
    style_notes: str,
) -> str:
    return f"""Create one horizontal animation row strip for the Codex App pet named {pet_name}.

State: {state}
Action: {action}
Source: use the canonical base pet and video references to preserve identity.
Description: {description}
Pet notes: {notes or "preserve the same identity, palette, proportions, face, and markings as the base"}
Style notes: {style_notes or "compact pixel-art-adjacent chibi digital pet, thick dark outline, simple palette, flat cel shading"}

Output requirements:
- exactly 8 distinct frames laid out left to right in one horizontal strip
- each frame contains one complete pose of the same pet
- all poses separated with clear padding; no pose crosses into a neighboring slot
- perfectly flat solid #00ff00 chroma-key background
- do not use #00ff00 inside the pet
- no visible grid, dividers, frame numbers, text, labels, UI, scenery, floor, cast shadow, contact shadow, glow, speed lines, wave marks, dust trails, or detached floating effects
- keep the same pet identity in every frame
"""


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, help="Source video, GIF, or movie file")
    parser.add_argument("--pet-name", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--pet-notes", default="")
    parser.add_argument("--style-notes", default="")
    parser.add_argument("--frames", type=int, default=12, help="Number of sampled reference frames")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    video = Path(args.video).expanduser().resolve()
    if not video.exists():
        raise SystemExit(f"video not found: {video}")
    if args.frames < 3:
        raise SystemExit("--frames must be at least 3")

    pet_name = args.pet_name.strip() or title_from_slug(video.stem)
    slug = slugify(pet_name)
    description = args.description.strip() or f"Video-derived Codex pet based on {video.stem}."
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else default_codex_home() / "pet-runs" / "video-hatch-pet" / f"{slug}-{timestamp}"
    )

    if run_dir.exists() and any(run_dir.iterdir()) and not args.force:
        raise SystemExit(f"{run_dir} already exists and is not empty; pass --force")
    run_dir.mkdir(parents=True, exist_ok=True)

    metadata = ffprobe(video)
    duration = duration_seconds(metadata)
    frame_dir = run_dir / "references" / "frames"
    frames: list[dict] = []
    for index in range(args.frames):
        ts = duration * (index + 0.5) / args.frames
        out_path = frame_dir / f"frame-{index:03d}.jpg"
        extract_frame(video, ts, out_path)
        frames.append({"index": index, "timestamp": round(ts, 3), "path": str(out_path)})

    contact_sheet = run_dir / "references" / "contact-sheet.jpg"
    create_contact_sheet(frames, contact_sheet)

    prompt_dir = run_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    base_prompt_path = prompt_dir / "base.txt"
    base_prompt_path.write_text(
        base_prompt(pet_name, description, args.pet_notes, args.style_notes),
        encoding="utf-8",
    )

    jobs = [
        {
            "id": "base",
            "kind": "base",
            "status": "pending",
            "prompt": str(base_prompt_path),
            "decoded_path": str(run_dir / "decoded" / "base.png"),
            "input_images": [
                {"path": str(contact_sheet), "role": "video reference contact sheet"}
            ],
        }
    ]
    for state, action in STATES:
        prompt_path = prompt_dir / f"{state}.txt"
        prompt_path.write_text(
            row_prompt(
                pet_name,
                state,
                action,
                description,
                args.pet_notes,
                args.style_notes,
            ),
            encoding="utf-8",
        )
        jobs.append(
            {
                "id": state,
                "kind": "row",
                "state": state,
                "status": "pending",
                "prompt": str(prompt_path),
                "decoded_path": str(run_dir / "decoded" / f"{state}.png"),
                "input_images": [
                    {"path": str(run_dir / "references" / "canonical-base.png"), "role": "canonical base pet"},
                    {"path": str(contact_sheet), "role": "video reference contact sheet"},
                ],
            }
        )

    request = {
        "schema": "video-hatch-pet.pet-request.v1",
        "created_at": iso_now(),
        "video": str(video),
        "pet_name": pet_name,
        "slug": slug,
        "description": description,
        "pet_notes": args.pet_notes,
        "style_notes": args.style_notes,
        "chroma_key": "#00ff00",
        "atlas": {"columns": 8, "rows": 9, "cell_width": 192, "cell_height": 208},
        "states": [state for state, _ in STATES],
        "frames": frames,
        "contact_sheet": str(contact_sheet),
    }
    write_json(run_dir / "pet_request.json", request)
    write_json(run_dir / "video-metadata.json", metadata)
    write_json(
        run_dir / "imagegen-jobs.json",
        {
            "schema": "video-hatch-pet.imagegen-jobs.v1",
            "created_at": iso_now(),
            "run_dir": str(run_dir),
            "jobs": jobs,
        },
    )
    write_json(
        run_dir / "qa" / "run-summary.json",
        {
            "ok": True,
            "run_dir": str(run_dir),
            "pet_name": pet_name,
            "description": description,
            "contact_sheet": str(contact_sheet),
            "jobs": [job["id"] for job in jobs],
        },
    )

    print(
        json.dumps(
            {
                "ok": True,
                "run_dir": str(run_dir),
                "contact_sheet": str(contact_sheet),
                "imagegen_jobs": str(run_dir / "imagegen-jobs.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
