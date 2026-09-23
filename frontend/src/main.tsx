import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "@/App";
import "@/index.css";
import { startPwa } from "@/lib/pwa";

// Registered before the first render so an installed app that launches offline
// is served from the cache rather than failing to load at all.
startPwa();

const root = document.getElementById("root");
if (!root) throw new Error("#root not found");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
