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
import { useIdleHide } from "@/hooks/use-idle-hide";
import { formatDate } from "@/lib/format-date";

const BASE_FRAME_DURATION_MS = 500;

export default function Home() {
  const [manifest, setManifest] = useState<TransformManifest | null>(null);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState(true);
  const [speed, setSpeed] = useState(2);
  const [showTitle, setShowTitle] = useState(true);
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

  const controlsVisible = useIdleHide(playing);

  // Auto-play when images are loaded
  useEffect(() => {
    if (ready && images.length > 1) {
      setPlaying(true);
    }
  }, [ready, images.length]);

  // Fade out title after 4 seconds
  useEffect(() => {
    if (ready) {
      const t = setTimeout(() => setShowTitle(false), 4000);
      return () => clearTimeout(t);
    }
  }, [ready]);

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
  const currentDate = currentEntry?.date ? formatDate(currentEntry.date) : "";

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-black select-none">
      <main className="flex-1 min-h-0 flex flex-col">
        <div
          ref={containerRef}
          className="flex-1 min-h-0 relative flex items-center justify-center cursor-none"
          style={{ cursor: controlsVisible ? "default" : "none" }}
          onClick={() => setPlaying((p) => !p)}
        >
          {!ready ? (
            <div className="flex items-center justify-center text-white/60">
              <div className="text-center">
                <div className="text-sm font-light tracking-wide">
                  Loading {loadedCount} of {total} images
                </div>
                <div className="w-48 h-px bg-white/20 mt-3 overflow-hidden mx-auto">
                  <div
                    className="h-full bg-white/60 transition-all duration-300"
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

              {/* Top gradient for date readability */}
              <div
                className="absolute inset-x-0 top-0 h-20 pointer-events-none transition-opacity duration-500"
                style={{
                  background: "linear-gradient(to bottom, rgba(0,0,0,0.5), transparent)",
                  opacity: controlsVisible ? 1 : 0,
                }}
              />

              {/* Date overlay */}
              <div
                className="absolute top-4 left-5 pointer-events-none transition-opacity duration-500"
                style={{ opacity: controlsVisible ? 1 : 0 }}
              >
                <div className="text-white/90 text-sm font-light tracking-widest drop-shadow-[0_1px_4px_rgba(0,0,0,0.9)]">
                  {currentDate}
                </div>
              </div>

              {/* Bottom gradient */}
              <div
                className="absolute bottom-0 left-0 right-0 pointer-events-none h-32 transition-opacity duration-700"
                style={{
                  background: "linear-gradient(to top, rgba(0,0,0,0.7), transparent)",
                  opacity: controlsVisible || showTitle ? 1 : 0,
                }}
              />

              {/* Title overlay — fades out after initial display */}
              <div
                className="absolute bottom-16 left-5 pointer-events-none transition-opacity duration-1000"
                style={{ opacity: showTitle ? 1 : 0 }}
              >
                <h1 className="text-white/90 text-xl font-light tracking-wide drop-shadow-[0_1px_4px_rgba(0,0,0,0.9)]">
                  Aurajoki
                </h1>
                <p className="text-white/40 text-xs font-light tracking-wider mt-0.5 drop-shadow-[0_1px_4px_rgba(0,0,0,0.9)]">
                  Turku — one year through a window
                </p>
              </div>
            </>
          )}
        </div>

        {ready && (
          <div
            className="shrink-0 px-5 pb-3 pt-2 space-y-1.5 transition-opacity duration-500"
            style={{ opacity: controlsVisible ? 1 : 0 }}
            onMouseEnter={() => {}}
          >
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
            />
          </div>
        )}
      </main>
    </div>
  );
}
