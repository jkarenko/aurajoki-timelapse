"use client";

import { Slider } from "@/components/ui/slider";
import type { ImageEntry } from "@/hooks/use-image-preloader";
import { formatDate, formatDateShort } from "@/lib/format-date";

interface TimelineProps {
  entries: ImageEntry[];
  currentFrame: number;
  alpha: number;
  onSeek: (frame: number) => void;
}

export function Timeline({ entries, currentFrame, alpha, onSeek }: TimelineProps) {
  const progress = currentFrame + alpha;

  const startDate = entries[0]?.date;
  const endDate = entries[entries.length - 1]?.date;
  const currentEntry = entries[currentFrame];

  return (
    <div className="space-y-1">
      <Slider
        value={[progress]}
        min={0}
        max={Math.max(entries.length - 1, 1)}
        step={0.01}
        onValueChange={([v]) => onSeek(v)}
        className="w-full"
      />
      <div className="flex justify-between text-[11px] text-white/40 font-light tracking-wider">
        <span>{startDate ? formatDateShort(startDate) : ""}</span>
        <span className="text-white/70">
          {currentEntry?.date ? formatDate(currentEntry.date) : ""}
        </span>
        <span>{endDate ? formatDateShort(endDate) : ""}</span>
      </div>
    </div>
  );
}
