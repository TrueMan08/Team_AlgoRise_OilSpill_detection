import axios from "axios";

const MODAL_BACKEND = "https://vscimatic999--oiltrace-backend-web.modal.run";
const LOCAL_BACKEND = "http://127.0.0.1:8000";
const RENDER_BACKEND = "https://sih-oil-spill-26143-backend.onrender.com";

function stripApiSuffix(url) {
  return String(url || "")
    .trim()
    .replace(/\/api\/v1\/?$/i, "")
    .replace(/\/$/, "");
}

const envPrimary =
  import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_BACKEND_PRIMARY_URL;

export const PRIMARY_HOST = stripApiSuffix(
  envPrimary || (import.meta.env.DEV ? LOCAL_BACKEND : MODAL_BACKEND)
);

export const FALLBACK_HOST = stripApiSuffix(
  import.meta.env.VITE_BACKEND_FALLBACK_URL || RENDER_BACKEND
);

export const isLocalBackend = /localhost|127\.0\.0\.1/i.test(PRIMARY_HOST);

const disableFailover =
  import.meta.env.VITE_DISABLE_BACKEND_FAILOVER === "true";

const useDevProxy =
  import.meta.env.DEV && import.meta.env.VITE_BACKEND_DIRECT !== "true";

export const PRIMARY_URL = useDevProxy ? "" : PRIMARY_HOST;
export const FALLBACK_URL = useDevProxy ? "/__backend-fallback" : FALLBACK_HOST;

let activeBase = PRIMARY_URL;

export function getActiveBackendUrl() {
  if (!activeBase || activeBase === PRIMARY_URL) return PRIMARY_HOST;
  if (activeBase === FALLBACK_URL) return FALLBACK_HOST;
  return activeBase;
}

export const apiClient = axios.create({
  baseURL: PRIMARY_URL,
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config) => {
  if (typeof FormData !== "undefined" && config.data instanceof FormData) {
    if (config.headers) {
      delete config.headers["Content-Type"];
      delete config.headers["content-type"];
    }
  }
  return config;
});

function shouldFailover(error, originalRequest) {
  if (disableFailover) return false;
  if (!originalRequest || originalRequest._retry) return false;
  const base = originalRequest.baseURL || PRIMARY_URL;
  if (base !== PRIMARY_URL) return false;
  const status = error.response?.status;
  const network = !error.response;
  const timeout = error.code === "ECONNABORTED";
  return network || timeout || (typeof status === "number" && status >= 500);
}

apiClient.interceptors.response.use(
  (response) => {
    if (response.config?.baseURL) {
      activeBase = response.config.baseURL;
    }
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    if (shouldFailover(error, originalRequest)) {
      originalRequest._retry = true;
      originalRequest.baseURL = FALLBACK_URL;
      activeBase = FALLBACK_URL;
      return apiClient(originalRequest);
    }
    return Promise.reject(error);
  }
);

export function describeBackendError(error) {
  if (!error) return "Unknown request failure.";
  const network = !error.response;
  if (import.meta.env.DEV && isLocalBackend && network) {
    return `Unable to connect to local backend (${PRIMARY_HOST}). Start it with: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`;
  }
  if (error.code === "ECONNABORTED") {
    return `Request timed out after ${Math.round((error.config?.timeout || 15000) / 1000)}s.`;
  }
  const data = error.response?.data;
  const detail = data?.detail ?? data?.message;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      /* ignore */
    }
  }
  if (error.response?.status) {
    return `${error.response.status}: ${error.response.statusText || "request failed"}`;
  }
  return error.message || "Backend request failed.";
}
