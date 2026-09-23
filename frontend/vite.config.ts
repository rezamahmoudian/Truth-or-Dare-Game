import { fileURLToPath, URL } from "node:url";

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

// The same values the design and index.css use, so the splash screen and the
// status bar match the first frame of the app instead of flashing a default.
const THEME_COLOR = "#1a0a2d";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Inside docker compose this is http://backend:8000; on a bare host it is
  // localhost. Either way the browser only ever talks to the Vite origin.
  const backend = env.BACKEND_ORIGIN ?? "http://localhost:8000";

  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        // "prompt", not "autoUpdate": a service worker that swaps itself in and
        // reloads the page would do it in the middle of someone's sentence.
        // The app shows a toast and reloads when they choose to.
        registerType: "prompt",
        injectRegister: false,
        includeAssets: [
          "icons/apple-touch-icon.png",
          "icons/favicon-32.png",
          "icons/favicon-64.png",
          "fonts/Vazirmatn[wght].woff2",
        ],
        manifest: {
          name: "جرأت — جرئت یا حقیقت",
          short_name: "جرأت",
          description:
            "با یک غریبه بازی کن، دوست پیدا کن و گفتگو را ادامه بده.",
          lang: "fa",
          dir: "rtl",
          start_url: "/",
          scope: "/",
          id: "/",
          display: "standalone",
          orientation: "portrait",
          background_color: THEME_COLOR,
          theme_color: THEME_COLOR,
          categories: ["social", "games", "entertainment"],
          icons: [
            { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
            { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
            {
              src: "/icons/maskable-192.png",
              sizes: "192x192",
              type: "image/png",
              purpose: "maskable",
            },
            {
              src: "/icons/maskable-512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
        },
        workbox: {
          // The shell — HTML, JS, CSS, the font, the icons — is precached so
          // the app opens instantly and opens at all on a bad connection.
          globPatterns: ["**/*.{js,css,html,woff2,png,svg,ico}"],
          // Client-side routes resolve to the shell; the server's own paths
          // must never be answered from the cache as if they were a page.
          navigateFallback: "/index.html",
          navigateFallbackDenylist: [/^\/api\//, /^\/ws\//, /^\/admin\//, /^\/static\//],
          cleanupOutdatedCaches: true,
          runtimeCaching: [
            {
              // Chat, game state and the lobby are live. A stale answer here
              // is worse than a failed request: it shows the wrong turn or a
              // message that was deleted, and nobody can tell it is stale.
              urlPattern: ({ url }) => url.pathname.startsWith("/api/"),
              handler: "NetworkOnly",
            },
          ],
        },
        devOptions: {
          // Off in development: a service worker caching the dev server's
          // modules makes hot reload lie about what is running.
          enabled: false,
        },
      }),
    ],
    // Mirrors the "@/*" paths entry in tsconfig.json — TypeScript resolves it
    // for type checking, Vite needs telling separately for the actual bundle.
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      host: true,
      port: 5173,
      strictPort: true,
      // Bind mounts on Windows/macOS do not deliver inotify events into the
      // container, so hot reload silently stops working without polling.
      watch: env.VITE_POLLING === "1" ? { usePolling: true, interval: 300 } : undefined,
      // Same-origin /api and /ws in development mirrors what Caddy does in
      // production. It keeps CORS out of the picture entirely and means no
      // API base URL has to be configured per environment.
      proxy: {
        "/api": { target: backend, changeOrigin: true },
        "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
        "/admin": { target: backend, changeOrigin: true },
        "/static": { target: backend, changeOrigin: true },
      },
    },
    preview: {
      host: true,
      port: 4173,
      // The preview server serves the real built bundle with the real service
      // worker — the only way to test installability short of deploying.
      proxy: {
        "/api": { target: backend, changeOrigin: true },
        "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
      },
    },
  };
});
