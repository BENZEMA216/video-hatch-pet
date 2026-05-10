# Codex Pet Format

## Package

Install packages live under:

```text
${CODEX_HOME:-$HOME/.codex}/pets/<slug>/
  pet.json
  spritesheet.webp
```

`pet.json`:

```json
{
  "id": "pet-slug",
  "displayName": "Pet Name",
  "description": "One sentence.",
  "spritesheetPath": "spritesheet.webp"
}
```

## Atlas Geometry

- Atlas size: `1536x1872`
- Columns: `8`
- Rows: `9`
- Cell size: `192x208`
- Final image mode: RGBA, saved as lossless WebP for installation

Rows, top to bottom:

1. `idle`
2. `waving`
3. `jumping`
4. `failed`
5. `review`
6. `running`
7. `running-right`
8. `running-left`
9. `celebrate`

Every row has 8 frames. Unused cells are not part of this skill's default contract; generate all 8 frames for every row.

## Row Strip Source Contract

Each `$imagegen` row result should be a single horizontal strip:

- 8 poses laid out left to right
- flat, uniform chroma-key background
- no visible grid, dividers, labels, or frame numbers
- generous padding around each pose
- complete pet silhouette in every pose
- no pose crossing into the next slot

The finalizer removes the sampled border chroma key, detects alpha-active subject groups, clusters them into 8 pose crops when possible, trims transparent padding, scales each pose into a 192x208 cell, and composes the final atlas. It falls back to equal-width slicing only when subject grouping cannot confidently produce 8 frames.

This matters because generated strips may contain off-slot poses or alpha-disconnected body parts such as curled tails. A row that produces detached fragments in `qa/contact-sheet.png` should be regenerated with stronger "tail attached" and "no detached body parts" constraints.

## Run Directory

The scripts use this structure:

```text
run/
  pet_request.json
  imagegen-jobs.json
  video-metadata.json
  references/
    contact-sheet.jpg
    canonical-base.png
    frames/frame-000.jpg
  prompts/base.txt
  prompts/<state>.txt
  decoded/base.png
  decoded/<state>.png
  final/spritesheet.png
  final/spritesheet.webp
  final/validation.json
  qa/contact-sheet.png
  qa/run-summary.json
```

`decoded/base.png` and `references/canonical-base.png` are created by `record_imagegen_result.py` after the base image is chosen. Row files under `decoded/` are selected `$imagegen` outputs, not local drawings.
