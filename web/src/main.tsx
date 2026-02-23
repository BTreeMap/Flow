import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./auth/AuthContext";
import { ThemeProvider } from "./ThemeProvider";
import { App } from "./App";
import "./index.css";
import "streamdown/styles.css";
import {
  readThemePreference,
  applyEffectiveThemeForPreference,
} from "./theme";

// Apply stored theme preference synchronously before first render to
// prevent a flash of the wrong theme on deep-linked routes.
applyEffectiveThemeForPreference(readThemePreference());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <ThemeProvider>
            <App />
          </ThemeProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
