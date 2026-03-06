"use client";

import { useEffect, useState, useRef } from "react";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export interface ImageEntry {
  filename: string;
  date: string;
  index: number;
  quality: string;
  skipped?: boolean;
}

export interface TransformManifest {
  canvas: { width: number; height: number };
  images: ImageEntry[];
}

export function useImagePreloader(manifest: TransformManifest | null) {
  const [images, setImages] = useState<HTMLImageElement[]>([]);
  const [loadedCount, setLoadedCount] = useState(0);
  const [ready, setReady] = useState(false);
  const loadingRef = useRef(false);

  const validImages = manifest?.images.filter((img) => !img.skipped) ?? [];

  useEffect(() => {
    if (!manifest || loadingRef.current) return;
    loadingRef.current = true;

    const loaded: HTMLImageElement[] = new Array(validImages.length);
    let count = 0;

    validImages.forEach((entry, i) => {
      const img = new Image();
      img.src = `${basePath}/aligned/${entry.filename}`;
      img.onload = () => {
        loaded[i] = img;
        count++;
        setLoadedCount(count);
        if (count === validImages.length) {
          setImages(loaded);
          setReady(true);
        }
      };
      img.onerror = () => {
        count++;
        setLoadedCount(count);
        if (count === validImages.length) {
          setImages(loaded.filter(Boolean));
          setReady(true);
        }
      };
    });
  }, [manifest]); // eslint-disable-line react-hooks/exhaustive-deps

  return { images, loadedCount, total: validImages.length, ready };
}
