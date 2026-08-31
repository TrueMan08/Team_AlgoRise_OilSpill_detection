// OilTrace frontend — API client.
// One configurable base URL; the backend is the single source of truth.
export const BACKEND_BASE_URL =
  import.meta.env.VITE_BACKEND_BASE_URL || "http://127.0.0.1:8000";

const V1 = `${BACKEND_BASE_URL}/api/v1`;

async function request(path, { method = "GET", body, timeoutMs = 180000 } = {}) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch (e) {
    clearTimeout(t);
    if (e.name === "AbortError")
      throw new Error("Request timed out. The backend may be starting up — please retry.");
    throw new Error("Cannot reach the backend. It may be starting (cold start) — please retry in a moment.");
  }
  clearTimeout(t);
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* ignore */ }
    if (res.status === 422)
      throw new Error(`Invalid input. Please check the selected slick and simulation parameters. ${detail}`);
    throw new Error(`Backend error (${res.status}). ${detail}`);
  }
  return res.json();
}

export const api = {
  health: () => request(`${V1}/health`, { timeoutMs: 8000 }),

  hindcast: (slick, durationHours = 12) =>
    request(`${V1}/hindcast`, { method: "POST", body: { slick, duration_hours: durationHours } }),

  vessels: (bbox, startIso, endIso) =>
    request(
      `${V1}/vessels?bbox=${encodeURIComponent(bbox)}&start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}`
    ),

  attribute: (incidentId, sourceRegion, vessels, uncertaintyRadiusKm = null) =>
    request(`${V1}/attribute`, {
      method: "POST",
      body: {
        incident_id: incidentId,
        source_region: sourceRegion,
        vessels,
        uncertainty_radius_km: uncertaintyRadiusKm,
      },
    }),

  // Uses the prebuilt forward_request from the selected attribution candidate.
  forward: (forwardRequest) =>
    request(`${V1}/forward`, { method: "POST", body: forwardRequest }),

  counterfactual: (incidentId, vesselMmsi, forwardResult, observedSlick) =>
    request(`${V1}/counterfactual`, {
      method: "POST",
      body: {
        incident_id: incidentId,
        vessel_mmsi: vesselMmsi,
        forward_result: forwardResult,
        observed_slick: observedSlick,
      },
    }),
};
