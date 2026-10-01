import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, API calls are proxied to the FastAPI server on port 8000.
// In production, FastAPI serves the built files from frontend/dist on the same origin.
const API = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(["/runs", "/runbook", "/metrics", "/auth", "/me", "/health", "/documents", "/tech-stacks"].map((p) => [p, API])),
  },
});
