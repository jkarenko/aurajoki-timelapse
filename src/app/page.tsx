"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MorphPlayer } from "@/components/morph-player";
import { Timeline } from "@/components/timeline";
import { Controls } from "@/components/controls";
import {
  useImagePreloader,
  type TransformManifest,
  type ImageEntry,
} from "@/hooks/use-image-preloader";
import { useAnimationLoop } from "@/hooks/use-animation-loop";

const BASE_FRAME_DURATION_MS = 500;

export default function Home() {
  const [manifest, setManifest] = useState<TransformManifest | null>(null);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState(true);
  const [speed, setSpeed] = useState(2);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/transforms.json")
      .then((res) => res.json())
      .then((data: TransformManifest) => setManifest(data));
  }, []);

  const { images, loadedCount, total, ready } = useImagePreloader(manifest);
  const validEntries: ImageEntry[] =
    manifest?.images.filter((img) => !img.skipped) ?? [];

  const { currentFrame, alpha, seekTo } = useAnimationLoop({
    frameCount: images.length,
    frameDurationMs: BASE_FRAME_DURATION_MS / speed,
    playing: playing && ready,
    loop,
  });

  // Auto-play when images are loaded
  useEffect(() => {
    if (ready && images.length > 1) {
      setPlaying(true);
    }
  }, [ready, images.length]);

  const handleSeek = useCallback(
    (position: number) => {
      setPlaying(false);
      seekTo(Math.floor(position));
    },
    [seekTo]
  );

  const stepFrame = useCallback(
    (delta: number) => {
      setPlaying(false);
      const next = Math.max(0, Math.min(currentFrame + delta, images.length - 1));
      seekTo(next);
    },
    [currentFrame, images.length, seekTo]
  );

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;

      switch (e.code) {
        case "Space":
          e.preventDefault();
          setPlaying((p) => !p);
          break;
        case "ArrowLeft":
          e.preventDefault();
          stepFrame(-1);
          break;
        case "ArrowRight":
          e.preventDefault();
          stepFrame(1);
          break;
        case "Home":
          e.preventDefault();
          seekTo(0);
          setPlaying(false);
          break;
        case "End":
          e.preventDefault();
          seekTo(images.length - 1);
          setPlaying(false);
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [stepFrame, seekTo, images.length]);

  const canvasWidth = manifest?.canvas.width ?? 1500;
  const canvasHeight = manifest?.canvas.height ?? 816;
  const currentEntry = validEntries[currentFrame];

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-black">
      <main className="flex-1 min-h-0 flex flex-col">
        <div
          ref={containerRef}
          className="flex-1 min-h-0 relative flex items-center justify-center"
        >
          {!ready ? (
            <div className="flex items-center justify-center text-muted-foreground">
              <div className="text-center">
                <div className="text-sm">
                  Loading images... {loadedCount}/{total}
                </div>
                <div className="w-48 h-1 bg-muted rounded-full mt-2 overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all"
                    style={{
                      width: `${total > 0 ? (loadedCount / total) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          ) : (
            <>
              <MorphPlayer
                images={images}
                currentFrame={currentFrame}
                alpha={alpha}
                canvasWidth={canvasWidth}
                canvasHeight={canvasHeight}
              />
              {/* Date overlay */}
              <div className="absolute top-4 left-4 pointer-events-none">
                <div className="text-white/90 text-sm font-mono tracking-wider drop-shadow-[0_1px_3px_rgba(0,0,0,0.8)]">
                  {currentEntry?.date ?? ""}
                </div>
              </div>
              {/* Title overlay */}
              <div className="absolute bottom-0 left-0 right-0 pointer-events-none bg-gradient-to-t from-black/60 to-transparent h-24" />
              <div className="absolute bottom-14 left-4 pointer-events-none">
                <h1 className="text-white/90 text-lg font-semibold tracking-tight drop-shadow-[0_1px_3px_rgba(0,0,0,0.8)]">
                  Aurajoki
                </h1>
                <p className="text-white/50 text-xs drop-shadow-[0_1px_3px_rgba(0,0,0,0.8)]">
                  Turku, one year through a window
                </p>
              </div>
            </>
          )}
        </div>

        {ready && (
          <div className="shrink-0 px-4 pb-3 pt-2 space-y-2 bg-black/80 backdrop-blur-sm">
            <Timeline
              entries={validEntries}
              currentFrame={currentFrame}
              alpha={alpha}
              onSeek={handleSeek}
            />
            <Controls
              playing={playing}
              onTogglePlay={() => setPlaying((p) => !p)}
              loop={loop}
              onToggleLoop={() => setLoop((l) => !l)}
              speed={speed}
              onSpeedChange={setSpeed}
              containerRef={containerRef}
              frameInfo={`${currentFrame + 1} / ${images.length}`}
            />
          </div>
        )}
      </main>
    </div>
  );
}
