import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served from the root, not a sub-path: this only ever runs on localhost.
export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ["react", "react-dom"] },
  server: { port: 5173 },
});
