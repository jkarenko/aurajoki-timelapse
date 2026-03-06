import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  basePath: "/aurajoki-timelapse",
  images: { unoptimized: true },
};

export default nextConfig;
