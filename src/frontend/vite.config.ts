import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Allow browser automation traffic from Docker-networked Chrome tooling.
    allowedHosts: ["frontend", "host.docker.internal", "localhost", "127.0.0.1"],
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
