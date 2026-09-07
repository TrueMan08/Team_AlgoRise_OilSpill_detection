import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

function originFromApiBase(raw, fallback) {
  const value = String(raw || fallback || "").trim();
  return value.replace(/\/api\/v1\/?$/i, "").replace(/\/$/, "") || fallback;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const localBackend = originFromApiBase(
    env.VITE_BACKEND_PROXY_TARGET || env.VITE_API_BASE_URL || env.VITE_BACKEND_PRIMARY_URL,
    "http://localhost:8000"
  );
  const useModalMl = env.VITE_USE_MODAL_ML === "true";

  const proxy = {
    "/api": {
      target: localBackend,
      changeOrigin: true,
      timeout: 180000,
    },
  };

  if (useModalMl) {
    proxy["/ml-api"] = {
      target: "https://vscimatic999--oiltrace-detection-web.modal.run",
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/ml-api/, ""),
    };
  }

  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy,
    },
  };
});
