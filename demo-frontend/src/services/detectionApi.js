/**
 * OilTrace Detection Service API client
 *
 * Live GeoTIFF inference is preferred through the orchestration backend
 * (`POST /api/v1/detect`) so the browser uses the same Axios failover as
 * hindcast/attribution. The Modal ML service remains available for the
 * cached demo scene (no CORS on that host — Vite proxies /ml-api).
 */

import { apiClient, describeBackendError } from "./api";

const BASE = import.meta.env.VITE_ML_BASE_URL || "/ml-api";

export function slicksToGeoJSON(slicks) {
  return {
    type: "FeatureCollection",
    features: (slicks || []).map((slick) => ({
      type: "Feature",
      id: slick.id,
      properties: {
        id: slick.id,
        confidence: slick.confidence,
        area_km2: slick.area_km2,
        centroid: slick.centroid,
        timestamp_utc: slick.timestamp_utc,
        sensor: slick.sensor,
        scene_id: slick.scene_id,
      },
      geometry: slick.geometry,
    })),
  };
}

export async function detectViaBackend(file, acquiredAtUtc) {
  const formData = new FormData();
  formData.append("image", file);
  if (acquiredAtUtc) formData.append("acquired_at_utc", acquiredAtUtc);
  try {
    const response = await apiClient.post("/api/v1/detect", formData, {
      timeout: 300000,
    });
    const payload = response.data;
    if (payload?.type === "FeatureCollection") return payload;
    if (Array.isArray(payload)) return slicksToGeoJSON(payload);
    if (payload?.id && payload?.geometry) return slicksToGeoJSON([payload]);
    return payload;
  } catch (error) {
    throw new Error(describeBackendError(error), { cause: error });
  }
}

/**
 * Fire-and-forget liveness probe. Wakes the container so subsequent
 * calls don't pay the cold-start penalty. Swallows all errors silently.
 * @returns {Promise<void>}
 */
export async function warmDetectionService() {
  try {
    await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(60_000) });
  } catch {
    // Intentionally silent — warm-up failure must never surface to the user.
  }
}

/**
 * Fetch the pre-computed demo detection result (no inference, instant).
 * This is the recommended integration entry point — real slick in the
 * Eastern Mediterranean, identical schema to a live POST /detect response.
 *
 * @returns {Promise<GeoJSONFeatureCollection>}
 * @throws {Error} with a user-readable message
 */
export async function fetchDemoDetection() {
  const response = await fetch(`${BASE}/detect/demo`, {
    signal: AbortSignal.timeout(120_000),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(
      `Demo detection failed (${response.status}): ${text || response.statusText}`
    );
  }

  return response.json();
}

/**
 * Run live inference on an uploaded GeoTIFF scene.
 *
 * @param {File} file       - GeoTIFF, exactly 2 bands (VV + VH), ≤ 80 MB
 * @param {number} [threshold] - Probability cutoff 0.05–0.95. Omit to use the
 *                               validated default (0.325).
 * @returns {Promise<GeoJSONFeatureCollection>}
 * @throws {Error} with a user-readable message
 */
export async function runLiveDetection(file, threshold) {
  const formData = new FormData();
  formData.append("file", file);

  const url = new URL(`${BASE}/detect`);
  if (threshold !== undefined) {
    url.searchParams.set("threshold", String(threshold));
  }

  const response = await fetch(url.toString(), {
    method: "POST",
    body: formData,
    // 300 s as specified in the API docs (20–60 s inference + cold-start margin)
    signal: AbortSignal.timeout(300_000),
  });

  if (!response.ok) {
    let detail;
    try {
      const json = await response.json();
      detail = json?.detail ?? json?.message ?? "";
    } catch {
      detail = await response.text().catch(() => "");
    }

    if (response.status === 413) {
      throw new Error("Upload exceeds the 80 MB limit. Please use a smaller scene.");
    }
    if (response.status === 422) {
      throw new Error(`Invalid file: ${detail || "Not a valid 2-band georeferenced GeoTIFF."}`);
    }
    if (response.status === 504) {
      throw new Error(
        "The detection service timed out (cold start). Please try again — the container is now warming."
      );
    }

    throw new Error(
      `Detection failed (${response.status}): ${detail || response.statusText}`
    );
  }

  return response.json();
}

/**
 * Download the demo GeoTIFF scene (24 MB) — useful for round-trip testing
 * POST /detect end-to-end.
 * @returns {Promise<Blob>}
 */
export async function fetchDemoScene() {
  const response = await fetch(`${BASE}/demo/scene`, {
    signal: AbortSignal.timeout(120_000),
  });
  if (!response.ok) {
    throw new Error(`Could not download demo scene (${response.status})`);
  }
  return response.blob();
}
