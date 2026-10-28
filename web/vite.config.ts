import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import { readFileSync, existsSync } from "node:fs";
import type { Plugin } from "vite";

// Dev server only: serve the unencrypted sample bundle (web/sample/*.json, gitignored) at
// /fantasy-desk/sample-bundle.json. configureServer never runs in `vite build`, so the
// sample can't leak into the deployed site.
function sampleData(): Plugin {
  return {
    name: "sample-data",
    configureServer(server) {
      server.middlewares.use("/fantasy-desk/sample-bundle.json", (_req, res) => {
        const leagues: Record<string, unknown> = {};
        for (const lg of ["basketball", "hockey", "soccer", "football"]) {
          const f = `sample/${lg}.json`;
          if (existsSync(f)) leagues[lg] = JSON.parse(readFileSync(f, "utf8"));
        }
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ generated_at: new Date().toISOString(), leagues }));
      });
    },
  };
}

// Served from https://robsanders818.github.io/fantasy-desk/
export default defineConfig({
  base: "/fantasy-desk/",
  plugins: [
    sampleData(),
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/apple-touch-icon.png"],
      manifest: {
        name: "Fantasy Desk",
        short_name: "Desk",
        description: "Daily lineup, add and win% recommendations",
        display: "standalone",
        background_color: "#0b0d10",
        theme_color: "#0b0d10",
        icons: [
          { src: "icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icons/icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
      workbox: {
        // Always fetch fresh data; cache only the app shell.
        navigateFallback: "index.html",
        runtimeCaching: [{ urlPattern: /\/data\//, handler: "NetworkFirst" }],
      },
    }),
  ],
});
