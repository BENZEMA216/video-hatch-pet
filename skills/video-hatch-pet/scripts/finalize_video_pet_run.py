#!/usr/bin/env python3
"""Finalize a video-hatch-pet run into a Codex pet package."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

CELL_W = 192
CELL_H = 208
COLUMNS = 8
STATES = [
    "idle",
    "waving",
    "jumping",
    "failed",
    "review",
    "running",
    "running-right",
    "running-left",
    "celebrate",
]
ATLAS_SIZE = (CELL_W * COLUMNS, CELL_H * len(STATES))


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser().resolve()


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-") or "video-pet"


def resolve_run_path(run_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else run_dir / path


def border_key_color(image: Image.Image) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    w, h = rgb.size
    samples = []
    for x in range(w):
        samples.append(rgb.getpixel((x, 0)))
        samples.append(rgb.getpixel((x, h - 1)))
    for y in range(h):
        samples.append(rgb.getpixel((0, y)))
        samples.append(rgb.getpixel((w - 1, y)))
    return Counter(samples).most_common(1)[0][0]


def is_green_screen_color(color: tuple[int, int, int]) -> bool:
    return color[1] > 180 and color[0] < 120 and color[2] < 120


def is_green_fringe_pixel(r: int, g: int, b: int, a: int) -> bool:
    return (
        a > 0
        and g > 24
        and g > r * 1.08
        and g > b * 1.08
        and g > r + 12
        and g > b + 12
    )


def remove_chroma_key(image: Image.Image, threshold: int = 42) -> Image.Image:
    rgba = image.convert("RGBA")
    key = border_key_color(rgba)
    out = []
    threshold_sq = threshold * threshold
    key_is_green_screen = is_green_screen_color(key)
    for r, g, b, a in rgba.getdata():
        dist = (r - key[0]) ** 2 + (g - key[1]) ** 2 + (b - key[2]) ** 2
        green_screen_pixel = key_is_green_screen and is_green_fringe_pixel(r, g, b, a)
        if a == 0 or dist <= threshold_sq or green_screen_pixel:
            out.append((0, 0, 0, 0))
        else:
            out.append((r, g, b, a))
    rgba.putdata(out)
    return rgba


def clear_green_fringe(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    out = []
    for r, g, b, a in rgba.getdata():
        if a == 0 or is_green_fringe_pixel(r, g, b, a):
            out.append((0, 0, 0, 0))
        else:
            out.append((r, g, b, a))
    rgba.putdata(out)
    return rgba


def trim_alpha(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
    return rgba.crop(bbox)


def fit_cell(image: Image.Image, clear_green: bool = False) -> Image.Image:
    subject = trim_alpha(image)
    if subject.width == 0 or subject.height == 0:
        return Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
    max_w = CELL_W - 24
    max_h = CELL_H - 24
    scale = min(max_w / subject.width, max_h / subject.height, 1.0)
    resized = subject.resize(
        (max(1, round(subject.width * scale)), max(1, round(subject.height * scale))),
        Image.Resampling.LANCZOS,
    )
    cell = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
    cell.alpha_composite(resized, ((CELL_W - resized.width) // 2, (CELL_H - resized.height) // 2))
    if clear_green:
        return clear_green_fringe(cell)
    return cell


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return image.convert("RGBA").getchannel("A").getbbox()


def subject_crops_from_strip(image: Image.Image) -> list[Image.Image]:
    alpha = image.getchannel("A")
    width, height = alpha.size
    alpha_data = alpha.load()
    active_columns = []
    for x in range(width):
        count = 0
        for y in range(height):
            if alpha_data[x, y]:
                count += 1
                if count >= 3:
                    active_columns.append(x)
                    break
    if not active_columns:
        return []

    groups: list[tuple[int, int]] = []
    start = prev = active_columns[0]
    for x in active_columns[1:]:
        if x - prev <= 3:
            prev = x
            continue
        groups.append((start, prev + 1))
        start = prev = x
    groups.append((start, prev + 1))

    if len(groups) > COLUMNS:
        gaps = [(groups[index + 1][0] - groups[index][1], index) for index in range(len(groups) - 1)]
        split_after = sorted(index for _, index in sorted(gaps, reverse=True)[: COLUMNS - 1])
        merged_groups: list[tuple[int, int]] = []
        group_start = 0
        for split_index in split_after:
            merged_groups.append((groups[group_start][0], groups[split_index][1]))
            group_start = split_index + 1
        merged_groups.append((groups[group_start][0], groups[-1][1]))
        groups = merged_groups

    crops: list[tuple[int, Image.Image]] = []
    for left, right in groups:
        segment = image.crop((left, 0, right, height))
        bbox = alpha_bbox(segment)
        if bbox is None:
            continue
        crop = segment.crop(bbox)
        coverage = alpha_coverage(crop)
        if crop.width >= 8 and crop.height >= 8 and coverage > 0.03:
            crops.append((left, crop))
    crops.sort(key=lambda item: item[1].width * item[1].height, reverse=True)
    crops = crops[:COLUMNS]
    crops.sort(key=lambda item: item[0])
    return [crop for _, crop in crops]


def split_strip(path: Path, chroma_threshold: int) -> list[Image.Image]:
    with Image.open(path) as source:
        key_is_green_screen = is_green_screen_color(border_key_color(source))
        rgba = remove_chroma_key(source, threshold=chroma_threshold)
    crops = subject_crops_from_strip(rgba)
    if len(crops) == COLUMNS:
        return [fit_cell(crop, clear_green=key_is_green_screen) for crop in crops]

    frame_w = rgba.width / COLUMNS
    frames = []
    for index in range(COLUMNS):
        left = round(index * frame_w)
        right = round((index + 1) * frame_w)
        frames.append(fit_cell(rgba.crop((left, 0, right, rgba.height)), clear_green=key_is_green_screen))
    return frames


def make_contact_sheet(atlas: Image.Image, out_path: Path) -> None:
    label_w = 120
    sheet = Image.new("RGBA", (label_w + ATLAS_SIZE[0], ATLAS_SIZE[1]), (255, 255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for row, state in enumerate(STATES):
        y = row * CELL_H
        draw.text((8, y + 12), state, fill=(20, 20, 20))
        draw.line((label_w, y, label_w + ATLAS_SIZE[0], y), fill=(220, 220, 220, 255))
    sheet.alpha_composite(atlas, (label_w, 0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(out_path)


def alpha_coverage(image: Image.Image) -> float:
    alpha = image.convert("RGBA").getchannel("A")
    hist = alpha.histogram()
    opaque = sum(hist[1:])
    return opaque / (image.width * image.height)


def visible_green_fringe_pixels(image: Image.Image) -> int:
    count = 0
    for r, g, b, a in image.convert("RGBA").getdata():
        if a >= 32 and is_green_fringe_pixel(r, g, b, a):
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--codex-home", default=str(default_codex_home()))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--chroma-threshold", type=int, default=42)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    request = load_json(run_dir / "pet_request.json")
    jobs_manifest = load_json(run_dir / "imagegen-jobs.json")
    jobs = {job["id"]: job for job in jobs_manifest.get("jobs", [])}

    missing = [state for state in STATES if jobs.get(state, {}).get("status") != "complete"]
    if missing:
        raise SystemExit(f"missing completed row jobs: {', '.join(missing)}")

    atlas = Image.new("RGBA", ATLAS_SIZE, (0, 0, 0, 0))
    validation_rows = []
    for row, state in enumerate(STATES):
        path = resolve_run_path(run_dir, jobs[state]["recorded_path"])
        frames = split_strip(path, args.chroma_threshold)
        row_coverages = []
        for col, frame in enumerate(frames):
            atlas.alpha_composite(frame, (col * CELL_W, row * CELL_H))
            row_coverages.append(round(alpha_coverage(frame), 4))
        validation_rows.append({"state": state, "source": str(path), "frame_alpha_coverage": row_coverages})

    final_dir = run_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    spritesheet_png = final_dir / "spritesheet.png"
    spritesheet_webp = final_dir / "spritesheet.webp"
    atlas.save(spritesheet_png)
    atlas.save(spritesheet_webp, format="WEBP", lossless=True, quality=100, method=6)

    make_contact_sheet(atlas, run_dir / "qa" / "contact-sheet.png")

    pet_name = request.get("pet_name") or "Video Pet"
    slug = request.get("slug") or slugify(pet_name)
    description = request.get("description") or f"Video-derived Codex pet named {pet_name}."
    pet_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else Path(args.codex_home).expanduser().resolve() / "pets" / slug
    )
    pet_dir.mkdir(parents=True, exist_ok=True)
    target_sheet = pet_dir / "spritesheet.webp"
    manifest_path = pet_dir / "pet.json"
    if not args.force and (target_sheet.exists() or manifest_path.exists()):
        raise SystemExit(f"{pet_dir} already contains pet files; pass --force to overwrite")
    shutil.copy2(spritesheet_webp, target_sheet)
    write_json(
        manifest_path,
        {
            "id": slug,
            "displayName": pet_name,
            "description": description,
            "spritesheetPath": "spritesheet.webp",
        },
    )

    green_fringe_pixels = visible_green_fringe_pixels(atlas)
    green_fringe_threshold = 500
    green_fringe_ok = green_fringe_pixels <= green_fringe_threshold
    validation = {
        "ok": green_fringe_ok,
        "created_at": iso_now(),
        "atlas_size": list(atlas.size),
        "cell_size": [CELL_W, CELL_H],
        "states": STATES,
        "rows": validation_rows,
        "green_fringe_pixels_alpha_ge_32": green_fringe_pixels,
        "green_fringe_threshold": green_fringe_threshold,
        "green_fringe_ok": green_fringe_ok,
        "spritesheet_png": str(spritesheet_png),
        "spritesheet_webp": str(spritesheet_webp),
        "pet_dir": str(pet_dir),
        "manifest": str(manifest_path),
    }
    write_json(final_dir / "validation.json", validation)
    write_json(
        run_dir / "qa" / "run-summary.json",
        {
            "ok": green_fringe_ok,
            "completed_at": iso_now(),
            "pet_name": pet_name,
            "pet_dir": str(pet_dir),
            "contact_sheet": str(run_dir / "qa" / "contact-sheet.png"),
            "validation": str(final_dir / "validation.json"),
        },
    )
    print(json.dumps({"ok": green_fringe_ok, "pet_dir": str(pet_dir), "validation": str(final_dir / "validation.json")}, indent=2))


if __name__ == "__main__":
    main()
