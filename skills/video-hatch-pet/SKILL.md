---
name: video-hatch-pet
description: Use when creating, repairing, validating, previewing, or packaging a Codex App animated pet from a source video, screen recording, GIF, or movie file. Use when a user wants a video-derived custom pet, video-to-spritesheet workflow, or installable Codex pet package without relying on the hatch-pet skill.
---

# Video Hatch Pet

## Overview

Create a Codex App installable animated pet from a video. This skill is self-contained for video ingestion, frame extraction, prompt planning, manifest management, atlas assembly, validation, QA artifacts, and local pet packaging; it depends on `$imagegen` only for generated bitmap art.

Do not import, call, or rely on the `hatch-pet` skill. If a detail is needed for the package format, use this skill's `references/pet-format.md` and bundled scripts.

## Core Rules

- Use `$imagegen` for pet visuals. Do not draw, tile, or synthesize pet art locally as a substitute.
- Use bundled scripts only for deterministic work: video frames, manifests, chroma-key cleanup, frame splitting, atlas assembly, QA, and packaging.
- Keep generated pet art in Codex digital pet style: compact chibi/pixel-adjacent mascot, thick readable outline, simple palette, clear silhouette, transparent final background.
- Generate row strips on a flat chroma-key background, usually `#00ff00`; the finalizer removes it.
- The final package must contain `pet.json` and `spritesheet.webp` under `${CODEX_HOME:-$HOME/.codex}/pets/<slug>/`.

Read `references/pet-format.md` when you need exact atlas geometry, row order, or manifest structure.

## Workflow

1. Load and follow `$imagegen` before any visual generation:

```text
${CODEX_HOME:-$HOME/.codex}/skills/.system/imagegen/SKILL.md
```

2. Prepare the run:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/video-hatch-pet"
python "$SKILL_DIR/scripts/prepare_video_pet_run.py" \
  --video /absolute/path/to/source-video.mp4 \
  --pet-name "<Name>" \
  --description "<one sentence>" \
  --force
```

The script writes a run directory with sampled frames, a contact sheet, prompt files, `pet_request.json`, and `imagegen-jobs.json`.

3. Inspect the contact sheet and sampled frames. Select the frame or small set of frames that best captures identity, color, proportions, and any signature movement. If the contact sheet is unclear, rerun preparation with more frames:

```bash
python "$SKILL_DIR/scripts/prepare_video_pet_run.py" \
  --video /absolute/path/to/source-video.mp4 \
  --frames 18 \
  --pet-name "<Name>" \
  --force
```

4. Generate and record the base image first. Use `$imagegen` with `prompts/base.txt`, the contact sheet, and any selected frame images as references. The base image should be a clean, single canonical pet on a flat chroma-key background. After choosing the generated output:

```bash
python "$SKILL_DIR/scripts/record_imagegen_result.py" \
  --run-dir /absolute/path/to/run \
  --job-id base \
  --source /absolute/path/to/generated-output.png
```

5. Generate and record every row job listed in `imagegen-jobs.json`. For each state, use its prompt file plus the canonical base image and useful source-video frames. Each row output should be one horizontal strip of 8 separated poses on the same flat chroma-key background.

```bash
python "$SKILL_DIR/scripts/record_imagegen_result.py" \
  --run-dir /absolute/path/to/run \
  --job-id idle \
  --source /absolute/path/to/generated-idle-strip.png
```

6. Finalize the package:

```bash
python "$SKILL_DIR/scripts/finalize_video_pet_run.py" \
  --run-dir /absolute/path/to/run \
  --force
```

Expected outputs:

```text
run/
  references/frames/
  references/contact-sheet.jpg
  prompts/
  decoded/
  final/spritesheet.png
  final/spritesheet.webp
  final/validation.json
  qa/contact-sheet.png
  qa/run-summary.json

${CODEX_HOME:-$HOME/.codex}/pets/<slug>/
  pet.json
  spritesheet.webp
```

7. Review `qa/contact-sheet.png`, `final/validation.json`, and the installed package. Deterministic validation is necessary but not sufficient; reject rows where identity, palette, body type, markings, prop placement, or silhouette drift from the base.

The final validation includes `green_fringe_pixels_alpha_ge_32`, `green_fringe_threshold`, and `green_fringe_ok`. Treat `green_fringe_ok: false` as a packaging failure for green-screen runs; inspect the QA contact sheet even when it is true.

## Animation States

Use these 9 rows in this exact order:

1. `idle` - calm breathing, blink, tiny bob.
2. `waving` - friendly paw/hand wave, no wave marks.
3. `jumping` - vertical bounce, no shadows or impact effects.
4. `failed` - disappointed/dizzy reaction, only attached effects if needed.
5. `review` - focused inspecting/reading posture, no UI or text.
6. `running` - busy in-place task loop, not literal travel.
7. `running-right` - directional movement to the right, no speed lines.
8. `running-left` - directional movement to the left, no speed lines.
9. `celebrate` - small success loop, no floating symbols unless attached and sprite-like.

## Quality Bar

Block final acceptance when any row has:

- visible grid, labels, frame numbers, text, UI, scenery, shadows, or floor patches
- detached sparkles, icons, speed lines, dust, smoke, wave marks, or motion trails
- overlapping poses that cross frame slots
- cropped body parts or unsafe padding
- chroma-key color inside the pet
- inconsistent identity versus the canonical base

If a row is visually wrong, regenerate that row through `$imagegen`, record the replacement with `record_imagegen_result.py`, and run `finalize_video_pet_run.py` again.

## Troubleshooting Notes

These issues came up during a real cat-video run and should be checked on every package:

- Row strips from `$imagegen` may not align poses to equal-width frame slots. If final sprites show tail fragments or chopped body parts, the finalizer should extract subjects from alpha column groups; if poses overlap or touch, regenerate that row.
- A single pose can contain multiple alpha-disconnected parts, such as a curled tail separated from the body by a few transparent pixels. When more than 8 alpha groups are present, group them into 8 pose clusters using the largest inter-pose gaps; if fragments remain, regenerate the row with explicit "tail attached to body" and "no detached body parts" constraints.
- Chroma-key pixels with alpha `0` can still keep green RGB values. If those pixels are resized, the green RGB bleeds into semi-transparent edges. The finalizer must zero RGB when making a pixel transparent.
- Green fringes can survive as dark green or yellow-green antialias pixels after resizing. The finalizer performs a second green-fringe cleanup after fitting each cell, then reports `green_fringe_pixels_alpha_ge_32` in validation.
- Dimension checks only prove that an atlas exists. They do not catch identity drift, mixed body proportions, row-order mistakes, leftover props, scenery, or subtle chroma-key edges. Always open `qa/contact-sheet.png`.
- If the user calls out a missing identity trait after QA, record it in `pet_request.json` and every prompt as an invariant, regenerate the canonical base, then regenerate all rows from that new base. Do not patch only one row unless the trait already appears consistently elsewhere.
- If `final/validation.json` has `ok: false`, do not call the pet complete. Fix the row art or the finalizer, rerun finalization, and re-check the QA artifacts.
