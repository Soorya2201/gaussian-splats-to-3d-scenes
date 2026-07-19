import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// host:true exposes the dev server on the LAN so the PICO OS 6 emulator can
// reach it at http://10.0.2.2:5173/ (see README, "Run in the PICO emulator").
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
  },
});
