# Video Hatch Pet

Create an installable Codex App animated pet from a source video without relying on the `hatch-pet` skill. The workflow is self-contained for video ingestion, frame extraction, prompt planning, manifest management, chroma-key cleanup, atlas assembly, validation, QA artifacts, and local pet packaging. It uses Codex `$imagegen` for the generated bitmap art.

## What Is Included

- `skills/video-hatch-pet/` - the Codex skill.
- `docs/xhs-dangdang-codex-pet.md` - a Chinese write-up draft for the Dangdang example.
- `xhs-cards/index.html` - screenshot-ready Xiaohongshu card layout.
- `xhs-cards/assets/` - generated example pet assets used by the card page.

The repository does not include the source cat video or extracted video frames.

## Install The Skill

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/video-hatch-pet "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Then restart Codex or reload skills.

## Use The Skill

Ask Codex to create a pet from a video, for example:

```text
Use video-hatch-pet to make an installable Codex pet from /absolute/path/to/cat.mp4.
The pet should preserve the cat's fluffy head tufts and playful personality.
```

The final package is installed under:

```text
${CODEX_HOME:-$HOME/.codex}/pets/<slug>/
  pet.json
  spritesheet.webp
```

## Requirements

- Codex App with local skills enabled.
- Python 3 with Pillow available.
- `ffmpeg` and `ffprobe` available on PATH for video sampling.
- `$imagegen` skill/tool for creating the pet art.

## Quality Lessons From Dangdang

- Generated row strips do not always align to 8 equal frame slots, so the finalizer detects alpha-active subject groups before falling back to equal slicing.
- Transparent chroma-key pixels must have RGB cleared too; otherwise green can bleed into resized sprite edges.
- Green-screen antialiasing can survive as dark green or yellow-green fringe, so the finalizer reports `green_fringe_pixels_alpha_ge_32`.
- A single pose can have alpha-disconnected parts, such as a curled tail separated by transparent pixels. Rows with remaining fragments should be regenerated with explicit body-part constraints.
- User-called-out traits, like Dangdang's messy head tufts, should become prompt invariants across the canonical base and every animation row.

## Example Output

Open `xhs-cards/index.html` in a browser to see the Dangdang case study cards.
