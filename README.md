# Aurajoki Timelapse

A timelapse viewer of the Aurajoki river in Turku, Finland. Built with Next.js — browse aligned webcam frames as a smooth animation with playback controls.

**[View the live site](https://jkarenko.github.io/aurajoki-timelapse/)**

## Features

- Frame-by-frame timelapse playback with adjustable speed
- Timeline scrubbing and keyboard controls
- Auto-hiding UI during playback
- Aligned images via a Python pipeline with homography matching

## Development

```bash
pnpm install
pnpm dev
```

## Image Pipeline

Source images are aligned using the Python pipeline in `pipeline/`:

```bash
pnpm align
```

This produces registered WebP frames in `public/aligned/` and a `public/transforms.json` manifest.

## Deployment

The site is statically exported and deployed to GitHub Pages via GitHub Actions on push to `main`.
