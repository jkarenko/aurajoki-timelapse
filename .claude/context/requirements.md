# Requirements

## Project Description
Website that shows animated morph transitions between time-series photos of the same architectural scene (Aura river view from a window in Turku). Photos taken handheld — varying position, angle, focal length between shots.

## Core Requirements
1. **Image alignment/registration**: State-of-the-art geometry matching (homography or similar) to handle translation, rotation, and focal length differences without cropping — no information loss
2. **Smooth morph animation**: Cross-dissolve/morph between aligned images so it plays like a video timelapse
3. **Backend processing**: Images matched and geometry transforms stored as JSON (or appropriate format for the chosen library)
4. **Frontend viewer**: Smooth playback with controls

## Tech Stack
- TypeScript + Node.js
- pnpm package manager
- shadcn/ui + Pencil for UI components and design
- Next.js (TBD — to be confirmed in architecture phase)

## Image Inventory
- ~140 photos spanning March 2025 – March 2026
- Mixed formats: jpg, JPG, webp, jpeg
- Subject: Aura river, buildings, road, floating restaurant — architectural scene from elevated window
- Taken at ~06:30 each morning (sunrise/dawn conditions vary by season)

## Constraints
- No cropping — preserve full image content
- Geometry transforms must be precomputed (not real-time)
- Animation must be smooth enough to look like video
