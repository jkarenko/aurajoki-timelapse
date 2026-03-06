"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Returns true when UI should be visible (mouse recently moved or not playing). */
export function useIdleHide(playing: boolean, timeoutMs = 3000) {
  const [visible, setVisible] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const resetTimer = useCallback(() => {
    setVisible(true);
    clearTimeout(timerRef.current);
    if (playing) {
      timerRef.current = setTimeout(() => setVisible(false), timeoutMs);
    }
  }, [playing, timeoutMs]);

  useEffect(() => {
    if (!playing) {
      setVisible(true);
      clearTimeout(timerRef.current);
      return;
    }

    resetTimer();

    const onMove = () => resetTimer();
    window.addEventListener("mousemove", onMove);
    window.addEventListener("touchstart", onMove);

    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("touchstart", onMove);
      clearTimeout(timerRef.current);
    };
  }, [playing, resetTimer]);

  return visible;
}
