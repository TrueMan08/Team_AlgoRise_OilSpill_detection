/**
 * OilTrace Backend API client + frontend-shape adapters.
 *
 * Live requests go through `src/services/api.js`.
 * Development: localhost:8000 (no Modal failover).
 * Production: Modal, optional Render fallback.
 *
 * All analytical outputs (source regions, rankings, trajectories, footprints,
 * counterfactual verdicts) come from these endpoints — never computed locally.
 */

import { apiClient, describeBackendError, getActiveBackendUrl, isLocalBackend } from "./api";

import {
  usingCanonicalRun,
  canonicalHindcast,
  canonicalVessels,
  canonicalAttribution,
  canonicalForward,
  canonicalCounterfactual,
  canonicalReplay,
  canonicalHealth,
} from "./demoData";

export { getActiveBackendUrl, isLocalBackend };
export const BACKEND_BASE = getActiveBackendUrl();

async function request(path, options = {}, timeoutMs = 120000) {
  const method = (options.method || "GET").toUpperCase();
  const headers = { ...(options.headers || {}) };
  try {
    const response = await apiClient.request({
      url: `/api/v1${path}`,
      method,
      data: options.body,
      headers,
      timeout: timeoutMs,
    });
    return response.data;
  } catch (error) {
    throw new Error(describeBackendError(error), { cause: error });
  }
}

/* ── Health / warm-up ─────────────────────────────────────────────── */

export const warmBackend = () =>
  usingCanonicalRun()
    ? Promise.resolve(canonicalHealth())
    : request("/health", {}, 60000).catch(() => null);
export const getBackendHealth = () =>
  usingCanonicalRun() ? Promise.resolve(canonicalHealth()) : request("/health", {}, 60000);
export const getBackendPing = () =>
  usingCanonicalRun() ? Promise.resolve({ ping: "pong" }) : request("/ping", {}, 60000);
export const getMlHealth = () => request("/health/ml", {}, 120000);

/* ── Investigation endpoints ──────────────────────────────────────── */

export function detectOilSpills(file, acquiredAtUtc) {
  const fd = new FormData();
  fd.append("image", file);
  if (acquiredAtUtc) fd.append("acquired_at_utc", acquiredAtUtc);
  return request("/detect", { method: "POST", body: fd }, 300000);
}

export function runHindcast(slick, durationHours = 6) {
  if (usingCanonicalRun()) return Promise.resolve(canonicalHindcast());
  return request(
    "/hindcast",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slick, duration_hours: durationHours }),
    },
    180000
  );
}

export function getCandidateVessels(bbox, start, end) {
  if (usingCanonicalRun()) return Promise.resolve(canonicalVessels());
  const q = new URLSearchParams({ bbox, start, end });
  return request(`/vessels?${q}`, {}, 120000);
}

export function runAttribution(incidentId, sourceRegion, vessels, uncertaintyRadiusKm = 10) {
  if (usingCanonicalRun()) return Promise.resolve(canonicalAttribution());
  return request(
    "/attribute",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        incident_id: incidentId,
        source_region: sourceRegion,
        vessels,
        uncertainty_radius_km: uncertaintyRadiusKm,
      }),
    },
    180000
  );
}

export function runForwardSimulation(forwardRequest) {
  // Rejects for a release state the canonical run never simulated, exactly as
  // the live endpoint would, so the caller records it as unavailable.
  if (usingCanonicalRun()) {
    try {
      return Promise.resolve(canonicalForward(forwardRequest));
    } catch (error) {
      return Promise.reject(error);
    }
  }
  return request(
    "/forward",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(forwardRequest),
    },
    180000
  );
}

export function runCounterfactual(incidentId, vesselMmsi, forwardResult, observedSlick) {
  if (usingCanonicalRun()) {
    try {
      return Promise.resolve(canonicalCounterfactual(vesselMmsi, forwardResult));
    } catch (error) {
      return Promise.reject(error);
    }
  }
  return request(
    "/counterfactual",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        incident_id: incidentId,
        vessel_mmsi: vesselMmsi,
        forward_result: forwardResult,
        observed_slick: observedSlick,
      }),
    },
    120000
  );
}

export function getReplay(id) {
  if (usingCanonicalRun()) return Promise.resolve(canonicalReplay());
  return request(`/replay/${encodeURIComponent(id)}`, {}, 120000);
}

/* ── Geometry helpers ─────────────────────────────────────────────── */

function rings(g) {
  if (!g) return [];
  if (g.type === "Polygon") return g.coordinates || [];
  if (g.type === "MultiPolygon") return (g.coordinates || []).flatMap((x) => x || []);
  return [];
}

export function bboxFromGeometry(g, pad = 0) {
  const pts = rings(g).flatMap((x) => x || []);
  if (!pts.length) throw new Error("Backend returned empty source-region geometry.");
  const xs = pts.map((p) => +p[0]).filter(Number.isFinite);
  const ys = pts.map((p) => +p[1]).filter(Number.isFinite);
  return [
    Math.min(...xs) - pad,
    Math.min(...ys) - pad,
    Math.max(...xs) + pad,
    Math.max(...ys) + pad,
  ].join(",");
}

/** Backend LineString ([lon, lat]) → [{latitude, longitude}, ...] */
export function trajectoryPoints(geometry) {
  if (!geometry || geometry.type !== "LineString") return [];
  return (geometry.coordinates || [])
    .map(([lon, lat]) => ({ latitude: +lat, longitude: +lon }))
    .filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude));
}

/* ── Backend → frontend shape adapters ────────────────────────────── */

/** Backend source_region → the sourceRegion shape the map/panels render. */
export function sourceRegionForFrontend(sr) {
  const c = sr?.candidate_regions?.[0];
  const centroid = c?.centroid || { lat: 0, lon: 0 };
  const pts = rings(c?.geometry).flatMap((x) => x || []);
  const ds = pts
    .map(([lon, lat]) =>
      Math.hypot(
        (+lat - centroid.lat) * 111.32,
        (+lon - centroid.lon) * 111.32 * Math.cos((centroid.lat * Math.PI) / 180)
      )
    )
    .filter(Number.isFinite);
  return {
    type: "Uncertainty region",
    center: { latitude: +centroid.lat, longitude: +centroid.lon },
    radiusMeters: Math.max(250, (ds.length ? Math.max(...ds) : 1) * 1000),
    confidence: Math.round(+(c?.probability || 0) * 100),
    isCalculated: true,
    geometry: c?.geometry,
    backendSourceRegion: sr,
  };
}

/** ML/backend detection feature → the Slick payload /hindcast expects. */
export function slickFromDetection(f) {
  const p = f?.properties || f;
  const g = f?.geometry || p.geometry;
  if (!g) throw new Error("No slick geometry is available for hindcast.");
  return {
    id: p.id || "detected-slick",
    timestamp_utc: p.timestamp_utc || null,
    centroid: { lat: +p.centroid.lat, lon: +p.centroid.lon },
    geometry: g,
    area_km2: +(p.area_km2 || 0),
    confidence: +(p.confidence || 0),
    sensor: p.sensor || "SAR",
    scene_id: p.scene_id || null,
  };
}

/** incident.json incident → the Slick payload /hindcast expects. */
export function slickFromIncident(i) {
  return {
    id: i.id,
    timestamp_utc: i.detectedAt,
    centroid: { lat: +i.centroid.latitude, lon: +i.centroid.longitude },
    geometry: {
      type: "Polygon",
      coordinates: [(i.spillPolygon || []).map(([lat, lon]) => [lon, lat])],
    },
    area_km2: +(i.areaKm2 || 0),
    confidence: +(i.detectionConfidence || 0),
    sensor: i.satellite?.sensor || "SAR",
    scene_id: i.satellite?.imageId || null,
  };
}

const DISPLAY_WEIGHTS = {
  spatial: 0.25, temporal: 0.25, trajectory: 0.2, drift: 0.2, aisReliability: 0.1,
};

/** Backend vessels + attribution → the vessel objects Sayan's UI renders. */
export function normalizeVessels(vessels, attr) {
  const am = new Map((attr?.all_attributions || []).map((a) => [String(a.mmsi), a]));
  const cm = new Map((attr?.top_candidates || []).map((a) => [String(a.vessel_mmsi), a]));
  return (vessels || [])
    .map((v) => {
      const pts = (v.track_points || [])
        .map((p) => ({
          time: p.timestamp_utc,
          latitude: +p.position.lat,
          longitude: +p.position.lon,
          speedKnots: p.sog == null ? null : +p.sog,
          heading: p.heading == null ? (p.cog == null ? null : +p.cog) : +p.heading,
        }))
        .filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude));
      const id = String(v.mmsi);
      const a = am.get(id);
      const c = cm.get(id);
      // Scores exist only when the backend attribution ran; never fabricate them.
      const hasAttr = Boolean(a || c);
      const isCulprit = v.is_culprit === true || v.isCulprit === true;
      const overall = hasAttr ? +(a?.overall_score ?? c?.overall_score ?? 0) : null;
      const rank = hasAttr ? +(a?.rank ?? c?.rank ?? 99) : null;
      const b = a?.evidence_breakdown || {};
      const rel = hasAttr
        ? +(c?.ais_reliability_score ?? (b.source_probability?.score != null ? b.source_probability.score / 100 : 0))
        : null;
      const sc = (x, fallback) => (x != null ? +x : fallback != null ? +fallback : 0);
      const ev = hasAttr
        ? {
            spatial: {
              score: sc(c?.spatial_score, b.spatial?.score != null ? b.spatial.score / 100 : 0),
              weight: b.spatial?.weight,
              label: b.spatial?.explanation || "Spatial proximity computed by backend attribution.",
            },
            temporal: {
              score: sc(c?.temporal_score, b.temporal?.score != null ? b.temporal.score / 100 : 0),
              weight: b.temporal?.weight,
              label: b.temporal?.explanation || "Temporal window computed by backend attribution.",
            },
            trajectory: {
              score: sc(c?.trajectory_score, b.trajectory?.score != null ? b.trajectory.score / 100 : 0),
              weight: b.trajectory?.weight,
              label: b.trajectory?.explanation || "Trajectory compatibility computed by backend attribution.",
            },
            // The counterfactual is a separate validation stage, not part of
            // the backend's attribution weighting — weight stays undefined.
            drift: { score: 0, label: "Counterfactual not run for this vessel." },
            aisReliability: {
              score: rel ?? 0,
              weight: b.source_probability?.weight,
              status: (rel ?? 0) >= 0.7 ? "Good" : (rel ?? 0) >= 0.4 ? "Warning" : "Critical",
              label: `AIS data reliability: ${((rel ?? 0) * 100).toFixed(1)}%. Hourly-bin coverage with gap penalty.`,
            },
          }
        : null;
      return {
        id: String(v.mmsi),
        mmsi: String(v.mmsi),
        name: v.name || `MMSI ${v.mmsi}`,
        type: v.vessel_type || "Vessel",
        flag: "AIS",
        position: pts.length
          ? { latitude: pts.at(-1).latitude, longitude: pts.at(-1).longitude }
          : null,
        speedKnots: pts.at(-1)?.speedKnots ?? null,
        heading: pts.at(-1)?.heading ?? 0,
        candidateRank: rank,
        attributionConfidence: overall == null ? null : Math.max(0, Math.min(1, overall / 100)),
        is_culprit: isCulprit,
        isCulprit,
        overallScore: overall,
        minDistanceKm: c?.min_distance_km ?? null,
        releaseLocation: c?.release_location ?? null,
        releaseTime: c?.release_time_utc ?? null,
        observationTime: c?.observation_time_utc ?? null,
        explanation: c?.explanation ?? null,
        aisGaps: v.ais_gaps || [],
        forwardRequest: c?.forward_request || null,
        evidence: ev,
        trajectory: pts,
        backend: { raw: v, attribution: a, candidate: c },
      };
    })
    .sort(
      (x, y) =>
        (x.candidateRank ?? 99) - (y.candidateRank ?? 99) ||
        (y.attributionConfidence ?? 0) - (x.attributionConfidence ?? 0)
    );
}

/** Backend-derived vessel → the `scoring` object the evidence panels render. */
export function buildFrontendScoring(v) {
  const e = v.evidence || {};
  const arr = [
    ["spatial", "Spatial Proximity", e.spatial],
    ["temporal", "Temporal Window", e.temporal],
    ["trajectory", "Trajectory Compatibility", e.trajectory],
    ["drift", "Drift / Counterfactual", e.drift],
    ["aisReliability", "AIS Reliability", e.aisReliability],
  ];
  const items = arr.map(([key, title, x]) => {
    const value = Math.round(Math.max(0, Math.min(1, +(x?.score || 0))) * 100);
    // Prefer the engine's own weight (evidence_breakdown[*].weight); the
    // display constants are only a fallback for the counterfactual signal.
    const weight = x?.weight ?? DISPLAY_WEIGHTS[key] ?? 0.2;
    return {
      key,
      title,
      short: key === "aisReliability" ? "AIS" : key.toUpperCase(),
      icon: key === "spatial" ? "⌖" : key === "temporal" ? "◷" : key === "trajectory" ? "↗" : key === "drift" ? "≈" : "◉",
      value,
      weight,
      weightedValue: Math.round(value * weight),
      description: x?.label || "Backend evidence signal.",
      status: x?.status,
    };
  });
  const confidence = Math.round((v.attributionConfidence || 0) * 100);
  return {
    confidence,
    overallScore: confidence,
    assessment:
      confidence >= 70
        ? "High attribution support"
        : confidence >= 40
          ? "Moderate attribution support"
          : "Low attribution support",
    assessmentClass: confidence >= 70 ? "strong" : confidence >= 40 ? "moderate" : "weak",
    evidenceItems: items,
    strongSignals: items.filter((x) => x.value >= 80).length,
    moderateSignals: items.filter((x) => x.value >= 60 && x.value < 80).length,
    weakSignals: items.filter((x) => x.value < 60).length,
    warnings:
      confidence < 40
        ? ["No strong candidate was returned by the backend attribution engine."]
        : [],
    weights: { ...DISPLAY_WEIGHTS },
  };
}

export function shiftIsoHours(iso, hours) {
  return new Date(new Date(iso).getTime() + hours * 3600 * 1000).toISOString();
}

export const CANONICAL_INCIDENT_ID = "incident-mediterranean-001";

export const CANONICAL_AIS_BBOX = "33.5,34.5,36.0,36.5";
export const CANONICAL_AIS_START = "2024-08-25T00:00:00Z";
export const CANONICAL_AIS_END = "2024-08-26T18:00:00Z";

export function latLngRingFromGeometry(g) {
  const ring = rings(g)[0] || [];
  return ring
    .map(([lon, lat]) => [+lat, +lon])
    .filter(([lat, lon]) => Number.isFinite(lat) && Number.isFinite(lon));
}

export function incidentFromDetection(feature, seed) {
  const slick = slickFromDetection(feature);
  return {
    ...seed,
    areaKm2: slick.area_km2 || seed.areaKm2,
    detectionConfidence: slick.confidence || seed.detectionConfidence,
    detectedAt: slick.timestamp_utc || seed.detectedAt,
    centroid: {
      latitude: slick.centroid.lat,
      longitude: slick.centroid.lon,
    },
    location: {
      latitude: slick.centroid.lat,
      longitude: slick.centroid.lon,
    },
    spillPolygon: latLngRingFromGeometry(slick.geometry).length
      ? latLngRingFromGeometry(slick.geometry)
      : seed.spillPolygon,
    satellite: {
      ...(seed.satellite || {}),
      imageId: slick.scene_id || seed.satellite?.imageId,
    },
    vessels: [],
  };
}

export function vesselsFromReplay(replay) {
  const frames = replay?.frames || [];
  const byMmsi = new Map();
  for (const frame of frames) {
    const time = frame.timestamp_utc;
    for (const vessel of frame.vessels || []) {
      const coords = vessel.position?.coordinates;
      const lon = Number(coords?.[0]);
      const lat = Number(coords?.[1]);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      const id = String(vessel.mmsi);
      const isCulprit = vessel.is_culprit === true || vessel.isCulprit === true;
      if (!byMmsi.has(id)) {
        // Replay frames carry AIS state only — no attribution has run, so
        // ranks, confidences, and evidence stay null until /attribute returns.
        byMmsi.set(id, {
          id,
          mmsi: id,
          name: vessel.name || `MMSI ${id}`,
          type: vessel.vessel_type || "Vessel",
          flag: "AIS",
          position: { latitude: lat, longitude: lon },
          speedKnots: null,
          heading: 0,
          candidateRank: null,
          attributionConfidence: null,
          overallScore: null,
          minDistanceKm: null,
          releaseLocation: null,
          releaseTime: null,
          observationTime: null,
          explanation: null,
          aisGaps: [],
          is_culprit: isCulprit,
          isCulprit,
          evidence: null,
          trajectory: [],
        });
      }
      const row = byMmsi.get(id);
      row.trajectory.push({ time, latitude: lat, longitude: lon });
      row.position = { latitude: lat, longitude: lon };
    }
  }
  return [...byMmsi.values()];
}

export function vesselsNearCentroid(vessels, centroid, maxDeg = 4) {
  const lat0 = +centroid?.latitude || +centroid?.lat;
  const lon0 = +centroid?.longitude || +centroid?.lon;
  if (!Number.isFinite(lat0) || !Number.isFinite(lon0)) return vessels || [];
  return (vessels || []).filter((vessel) => {
    const lat = +vessel.position?.latitude;
    const lon = +vessel.position?.longitude;
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
    return Math.abs(lat - lat0) <= maxDeg && Math.abs(lon - lon0) <= maxDeg;
  });
}

/* ── Forcing-data coverage guard ──────────────────────────────────── */
// Canonical SIH demo: Eastern Mediterranean CMEMS/ERA5 window.
export const FORCING_COVERAGE = {
  minLon: 33.5, maxLon: 36.0, minLat: 34.5, maxLat: 36.5,
  startUtc: "2024-08-25T00:00:00Z", endUtc: "2024-08-27T00:00:00Z",
};

export function assertWithinForcingCoverage(slick) {
  const { lat, lon } = slick?.centroid || {};
  const t = Date.parse(slick?.timestamp_utc);
  const c = FORCING_COVERAGE;
  const inSpace = lon >= c.minLon && lon <= c.maxLon && lat >= c.minLat && lat <= c.maxLat;
  const inTime = Number.isFinite(t) && t >= Date.parse(c.startUtc) && t <= Date.parse(c.endUtc);
  if (!inSpace || !inTime) {
    throw new Error(
      `This slick (${(+lat).toFixed(2)}°N, ${(+lon).toFixed(2)}°E, ${slick?.timestamp_utc}) is outside ` +
      `the Mediterranean forcing-data coverage (${c.minLon}–${c.maxLon}°E, ${c.minLat}–${c.maxLat}°N, ` +
      `25–26 Aug 2024 UTC). OpenDrift cannot run without currents/wind for that location and time.`
    );
  }
}

export function describeHindcastFailure(message) {
  const msg = String(message || "");
  if (/north\s*sea|norway|norkyst|nwshelf/i.test(msg)) {
    return "OpenDrift has North Sea forcing data, so a Cyprus hindcast cannot read currents or wind. Showing reconstructed physical drift.";
  }
  if (/Missing variables|first timestep|x_sea_water_velocity|x_wind|y_wind/i.test(msg)) {
    return "OpenDrift forcing data coverage mismatch for this scene. Showing reconstructed physical drift.";
  }
  if (/hdf|netcdf/i.test(msg)) {
    return "Forcing NetCDF is unreadable. Showing reconstructed physical drift.";
  }
  if (/Unknown incident/i.test(msg)) {
    return "This backend has not published incident-mediterranean-001 yet.";
  }
  return null;
}

export function describeEmptyMediterraneanAis() {
  return "GET /vessels for 33.5–36°E / 34.5–36.5°N (25–26 Aug 2024) returned no ships. The deployed AIS sample is still Norway-only, so none are drawn here.";
}

/**
 * Real AIS position of a normalized vessel at an exact UTC instant.
 *
 * Interpolates between the two surrounding timestamped AIS points. Returns
 * null when the instant falls outside the vessel's own track — callers must
 * treat that as "no valid AIS release state" rather than inventing one.
 * This is the single place AIS timestamps are turned into a position.
 */
export function aisPositionAt(vessel, tMs) {
  const pts = (vessel?.trajectory || [])
    .map((p) => ({ ms: Date.parse(p.time), lat: +p.latitude, lon: +p.longitude }))
    .filter((p) => Number.isFinite(p.ms) && Number.isFinite(p.lat) && Number.isFinite(p.lon))
    .sort((a, b) => a.ms - b.ms);
  if (pts.length < 2 || !Number.isFinite(tMs)) return null;
  if (tMs < pts[0].ms || tMs > pts[pts.length - 1].ms) return null;
  let i = 1;
  while (i < pts.length && pts[i].ms < tMs) i++;
  const a = pts[i - 1];
  const b = pts[i] || a;
  const f = b.ms === a.ms ? 0 : (tMs - a.ms) / (b.ms - a.ms);
  return {
    lat: a.lat + (b.lat - a.lat) * f,
    lon: a.lon + (b.lon - a.lon) * f,
  };
}
