"use client";

import { Slider } from "@/components/ui/slider";
import type { ImageEntry } from "@/hooks/use-image-preloader";

interface TimelineProps {
  entries: ImageEntry[];
  currentFrame: number;
  alpha: number;
  onSeek: (frame: number) => void;
}

export function Timeline({ entries, currentFrame, alpha, onSeek }: TimelineProps) {
  const progress = currentFrame + alpha;
  const currentEntry = entries[currentFrame];

  return (
    <div className="space-y-2">
      <Slider
        value={[progress]}
        min={0}
        max={Math.max(entries.length - 1, 1)}
        step={0.01}
        onValueChange={([v]) => onSeek(v)}
        className="w-full"
      />
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{entries[0]?.date ?? ""}</span>
        <span className="font-medium text-foreground">
          {currentEntry?.date ?? ""}
        </span>
        <span>{entries[entries.length - 1]?.date ?? ""}</span>
      </div>
    </div>
  );
}
