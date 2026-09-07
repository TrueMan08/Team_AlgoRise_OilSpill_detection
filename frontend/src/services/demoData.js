/**
 * Presentation data source for the canonical Eastern Mediterranean run.
 *
 * WHAT THIS IS
 * ------------
 * `canonicalRun.json` holds the verbatim backend responses for the canonical
 * incident, captured from the real pipeline (OpenDrift/OpenOil driven by CMEMS
 * currents and ERA5 wind, then AIS attribution and the counterfactual
 * comparison). Nothing in it is authored by hand: every geometry, trajectory,
 * timestamp and score is exactly what the backend returned.
 *
 * WHY IT EXISTS
 * -------------
 * The public deployment is open to anyone. Each hindcast, forward run and
 * attribution pass is a real physics computation on metered infrastructure, so
 * an unattended audience can exhaust the compute budget in minutes. When this
 * source is active the UI replays the canonical run instead of recomputing it.
 *
 * WHAT IT DOES NOT DO
 * -------------------
 * It does not reimplement any analysis. There is no physics, no scoring and no
 * geometry maths here. It is a lookup that returns stored responses in exactly
 * the shape the live endpoints return, so every adapter, component, animation
 * and state transition downstream is byte-for-byte the same code path.
 *
 * SELECTING THE SOURCE
 * --------------------
 *   ?mode=live   run against the real backend, and remember that choice
 *   ?mode=demo   replay the canonical run, and remember that choice
 * With no override, production builds replay the canonical run and development
 * builds call the backend, so local work against the API is unaffected.
 */

import canonicalRun from "../data/canonicalRun.json";

const STORAGE_KEY = "oiltrace.dataSource";
const LIVE = "live";
const CANONICAL = "canonical";

/** Structured clone so a caller can never mutate the stored run. */
const copy = (value) => JSON.parse(JSON.stringify(value));

function readOverride() {
  if (typeof window === "undefined") return null;
  let override = null;
  try {
    const mode = new URLSearchParams(window.location.search).get("mode");
    if (mode === "live") override = LIVE;
    if (mode === "demo" || mode === "canonical") override = CANONICAL;
  } catch {
    /* URL unavailable; fall through to stored preference */
  }
  try {
    if (override) {
      window.localStorage.setItem(STORAGE_KEY, override);
      return override;
    }
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === LIVE || stored === CANONICAL) return stored;
  } catch {
    /* storage blocked (private window); use the build default */
  }
  return override;
}

/** True when the UI should replay the canonical run instead of calling out. */
export function usingCanonicalRun() {
  const override = readOverride();
  if (override) return override === CANONICAL;
  return Boolean(import.meta.env.PROD);
}

/* ── Stored responses, in live endpoint shape ─────────────────────── */

export const canonicalDetection = () => copy(canonicalRun.detection);
export const canonicalReplay = () => copy(canonicalRun.replay);
export const canonicalHindcast = () => copy(canonicalRun.hindcast);
export const canonicalVessels = () => copy(canonicalRun.vessels);
export const canonicalAttribution = () => copy(canonicalRun.attribution);

/**
 * Forward runs are stored per release state, keyed by MMSI and release time,
 * so a vessel's own attributed run and the shared common-time run stay
 * separate and one candidate can never be served another's result.
 */
// The caller may hand us a timestamp it re-serialised through Date, so both
// sides of the lookup are canonicalised: "...T06:00:00Z" and
// "...T06:00:00.000Z" are the same release state and must resolve alike.
function normaliseIso(value) {
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? new Date(ms).toISOString() : String(value);
}

const releaseKey = (mmsi, releaseTimeUtc) =>
  `${mmsi}|${normaliseIso(releaseTimeUtc)}`;

export function canonicalForward(forwardRequest) {
  const key = releaseKey(
    String(forwardRequest?.vessel_mmsi),
    forwardRequest?.release_time_utc
  );
  const stored = canonicalRun.forward[key];
  if (!stored) {
    // Same failure the live path produces for a release state that was never
    // simulated. The caller turns this into its "unavailable" note.
    throw new Error(
      `No forward simulation is available for ${key} in the canonical run.`
    );
  }
  return copy(stored);
}

export function canonicalCounterfactual(vesselMmsi, forwardResult) {
  const key = releaseKey(String(vesselMmsi), forwardResult?.release_time_utc);
  const stored = canonicalRun.counterfactual[key];
  if (!stored) {
    throw new Error(
      `No counterfactual comparison is available for ${key} in the canonical run.`
    );
  }
  return copy(stored);
}

/** Health shape the status indicator expects, without a network round trip. */
export function canonicalHealth() {
  return {
    status: "healthy",
    version: canonicalRun._meta?.version || "0.1.0",
    environment: "production",
    timestamp: new Date().toISOString(),
  };
}
