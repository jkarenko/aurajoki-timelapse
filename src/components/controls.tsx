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
  frameInfo: string;
}

export function Controls({
  playing,
  onTogglePlay,
  loop,
  onToggleLoop,
  speed,
  onSpeedChange,
  containerRef,
  frameInfo,
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
    <div className="flex items-center gap-3">
      <Button
        variant="outline"
        size="icon"
        onClick={onTogglePlay}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>

      <Toggle
        pressed={loop}
        onPressedChange={onToggleLoop}
        aria-label="Toggle loop"
        size="sm"
      >
        <Repeat className="h-4 w-4" />
      </Toggle>

      <div className="flex items-center gap-2 min-w-[140px]">
        <span className="text-xs text-muted-foreground whitespace-nowrap">Speed</span>
        <Slider
          value={[speed]}
          min={0.5}
          max={10}
          step={0.5}
          onValueChange={([v]) => onSpeedChange(v)}
          className="w-20"
        />
        <span className="text-xs text-muted-foreground w-8">{speed}x</span>
      </div>

      <span className="text-xs text-muted-foreground ml-auto">{frameInfo}</span>

      <Button
        variant="outline"
        size="icon"
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
  );
}
