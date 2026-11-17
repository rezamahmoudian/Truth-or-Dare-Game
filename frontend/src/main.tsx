import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";

import App from "@/App";
import "@/index.css";
import { startPwa } from "@/lib/pwa";
import { ErrorBoundary } from "@/ui/ErrorBoundary";

// Registered before the first render so an installed app that launches offline
// is served from the cache rather than failing to load at all.
startPwa();

// A separate, development-only sandbox: no login, requests or financial state mutations.
const DesignPreview = import.meta.env.DEV && window.location.pathname === "/design/shop"
  ? lazy(() => import("@/features/shop/ShopDesignPreview")) : null;

const root = document.getElementById("root");
if (!root) throw new Error("#root not found");

createRoot(root).render(
  <StrictMode>
    {/* The outer net: the one inside the router covers the screens, this one
        covers everything before a router exists — splash, onboarding, the
        session bootstrap. */}
    <ErrorBoundary>
      {DesignPreview ? <Suspense fallback={<p className="p-6 text-center">در حال آماده‌سازی طرح…</p>}><DesignPreview /></Suspense> : <App />}
    </ErrorBoundary>
  </StrictMode>,
);
