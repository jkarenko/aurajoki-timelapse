"use client";

import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Toggle } from "@/components/ui/toggle";
import {
  Play,
  Pause,
  Repeat,
  Maximize,
  Minimize,
} from "lucide-react";
import { useCallback, useState } from "react";

interface ControlsProps {
  playing: boolean;
  onTogglePlay: () => void;
  loop: boolean;
  onToggleLoop: () => void;
  speed: number;
  onSpeedChange: (speed: number) => void;
  containerRef: React.RefObject<HTMLDivElement | null>;
}

export function Controls({
  playing,
  onTogglePlay,
  loop,
  onToggleLoop,
  speed,
  onSpeedChange,
  containerRef,
}: ControlsProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
      setIsFullscreen(false);
    } else {
      containerRef.current.requestFullscreen();
      setIsFullscreen(true);
    }
  }, [containerRef]);

  return (
    <div className="flex items-center gap-2">
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-white/70 hover:text-white hover:bg-white/10"
        onClick={(e) => {
          e.stopPropagation();
          onTogglePlay();
        }}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>

      <Toggle
        pressed={loop}
        onPressedChange={onToggleLoop}
        aria-label="Toggle loop"
        size="sm"
        className="h-8 w-8 text-white/40 hover:text-white hover:bg-white/10 data-[state=on]:text-white/80 data-[state=on]:bg-white/10"
      >
        <Repeat className="h-3.5 w-3.5" />
      </Toggle>

      <div className="flex items-center gap-1.5 ml-2">
        <span className="text-[11px] text-white/40 font-light">Speed</span>
        <Slider
          value={[speed]}
          min={0.5}
          max={10}
          step={0.5}
          onValueChange={([v]) => onSpeedChange(v)}
          className="w-16"
        />
        <span className="text-[11px] text-white/50 font-light w-6 tabular-nums">{speed}x</span>
      </div>

      <div className="ml-auto">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-white/40 hover:text-white hover:bg-white/10"
          onClick={toggleFullscreen}
          aria-label="Toggle fullscreen"
        >
          {isFullscreen ? (
            <Minimize className="h-4 w-4" />
          ) : (
            <Maximize className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  );
}
