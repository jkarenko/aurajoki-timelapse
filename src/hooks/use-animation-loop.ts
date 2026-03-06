"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UseAnimationLoopOptions {
  frameCount: number;
  frameDurationMs: number;
  playing: boolean;
  loop: boolean;
}

export function useAnimationLoop({
  frameCount,
  frameDurationMs,
  playing,
  loop,
}: UseAnimationLoopOptions) {
  const [currentFrame, setCurrentFrame] = useState(0);
  const [alpha, setAlpha] = useState(0);
  const rafRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);
  const progressRef = useRef(0); // 0 to frameCount-1 (fractional)

  const seekTo = useCallback(
    (frame: number) => {
      progressRef.current = Math.max(0, Math.min(frame, frameCount - 1));
      setCurrentFrame(Math.floor(progressRef.current));
      setAlpha(progressRef.current % 1);
    },
    [frameCount]
  );

  useEffect(() => {
    if (!playing || frameCount < 2) return;

    const animate = (time: number) => {
      if (lastTimeRef.current === 0) {
        lastTimeRef.current = time;
      }

      const delta = time - lastTimeRef.current;
      lastTimeRef.current = time;

      const frameAdvance = delta / frameDurationMs;
      progressRef.current += frameAdvance;

      if (progressRef.current >= frameCount - 1) {
        if (loop) {
          progressRef.current = 0;
        } else {
          progressRef.current = frameCount - 1;
          setCurrentFrame(frameCount - 2);
          setAlpha(1);
          return;
        }
      }

      const frame = Math.floor(progressRef.current);
      const a = progressRef.current - frame;
      setCurrentFrame(frame);
      setAlpha(a);

      rafRef.current = requestAnimationFrame(animate);
    };

    lastTimeRef.current = 0;
    rafRef.current = requestAnimationFrame(animate);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, frameCount, frameDurationMs, loop]);

  return { currentFrame, alpha, seekTo };
}
