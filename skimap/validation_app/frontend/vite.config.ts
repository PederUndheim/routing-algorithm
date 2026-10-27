import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The Pages base (/routing-algorithm/validering/) is passed on the command line
// by the deploy workflow, so the dev server still serves from the root.
export default defineConfig({
  plugins: [react()],
  server: { port: 5174 },
  test: { environment: "jsdom" },
});
