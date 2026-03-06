# ADR 001: Image Registration Pipeline

## Status
Accepted

## Context
~140 handheld photos of the same architectural scene need geometric alignment for smooth morph animation. Images vary in position, angle, and focal length. No cropping allowed.

## Decision
Use Python (opencv-python) via uv for the offline preprocessing pipeline:
- SIFT feature detection + FLANN matching + RANSAC homography
- Pre-warp all images to a common reference frame (auto-selected most centered image)
- Expand canvas to preserve all pixels (no crop)
- Output pre-warped images at 1500px on the longer side, uniform aspect ratio
- Store transforms as JSON (homography matrix, translation, canvas dims, match quality)
- TypeScript orchestrator spawns Python via child_process

Web app is Next.js + TypeScript + shadcn/ui + Pencil, rendering pre-warped images via Canvas2D crossfade.

## Alternatives Considered
- **OpenCV.js (WASM)**: SIFT unavailable in WASM build, Node.js environment bugs, manual memory management
- **sharp + custom homography**: No feature detection capability
- **Client-side CSS transforms**: More complex, less reliable quality than pre-warped images

## Consequences
- Python + uv required in dev environment (not in production)
- Pre-warped images increase storage (~140 images at 1500px)
- One-time offline computation, simple to re-run if new images are added
