import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The corridor images and index are the validation app's (validation_app/
// prepare.py), used as they are rather than copied: the same files, so the
// meeting sees exactly what the experts saw. Read only - Vite copies them
// into this build's output.
//
// The Pages base (/routing-algorithm/konsensus/) is passed on the command line
// by the deploy workflow, so the dev server still serves from the root.
export default defineConfig({
  plugins: [react()],
  publicDir: "../../validation_app/frontend/public",
  server: { port: 5175 },
  test: { environment: "jsdom" },
});
