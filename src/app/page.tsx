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

  const handleSeek = useCallback(
    (frame: number) => {
      setPlaying(false);
      seekTo(frame);
    },
    [seekTo]
  );

  const canvasWidth = manifest?.canvas.width ?? 1500;
  const canvasHeight = manifest?.canvas.height ?? 816;

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b px-6 py-3">
        <h1 className="text-lg font-semibold tracking-tight">Aurajoki</h1>
        <p className="text-xs text-muted-foreground">
          Turku, one year through a window
        </p>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center p-4 gap-4 max-w-[1600px] mx-auto w-full">
        <div ref={containerRef} className="w-full bg-black rounded-lg overflow-hidden">
          {!ready ? (
            <div
              className="flex items-center justify-center text-muted-foreground"
              style={{ aspectRatio: `${canvasWidth}/${canvasHeight}` }}
            >
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
            <MorphPlayer
              images={images}
              currentFrame={currentFrame}
              alpha={alpha}
              canvasWidth={canvasWidth}
              canvasHeight={canvasHeight}
            />
          )}
        </div>

        {ready && (
          <div className="w-full space-y-3">
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
