import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "./styles/tokens.generated.css";
import "./styles/global.css";
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { appRoutes } from "./app/router";
import { createQueryClient } from "./lib/queryClient";

const client = createQueryClient();
const router = createBrowserRouter(appRoutes);
const root = document.getElementById("root");
if (!root) throw new Error("index.html has no root element");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
