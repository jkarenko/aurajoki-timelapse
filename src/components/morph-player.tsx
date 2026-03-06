"use client";

import { useEffect, useRef } from "react";

interface MorphPlayerProps {
  images: HTMLImageElement[];
  currentFrame: number;
  alpha: number;
  canvasWidth: number;
  canvasHeight: number;
}

export function MorphPlayer({
  images,
  currentFrame,
  alpha,
  canvasWidth,
  canvasHeight,
}: MorphPlayerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || images.length < 2) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const frameA = images[currentFrame];
    const frameB = images[Math.min(currentFrame + 1, images.length - 1)];

    if (!frameA && !frameB) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (frameA) {
      ctx.globalAlpha = 1;
      ctx.drawImage(frameA, 0, 0, canvas.width, canvas.height);
    }

    if (frameB && alpha > 0 && currentFrame < images.length - 1) {
      ctx.globalAlpha = alpha;
      ctx.drawImage(frameB, 0, 0, canvas.width, canvas.height);
    }

    ctx.globalAlpha = 1;
  }, [images, currentFrame, alpha, canvasWidth, canvasHeight]);

  return (
    <canvas
      ref={canvasRef}
      width={canvasWidth}
      height={canvasHeight}
      className="w-full h-auto rounded-lg"
    />
  );
}
