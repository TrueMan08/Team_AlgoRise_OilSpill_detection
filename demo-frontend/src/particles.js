// OpenDrift-style particle cloud rendering.
//
// The backend returns the model's centroid trajectory, its timestamps, and the
// spatial envelopes (source region / predicted footprint). This module renders
// that output as an animated cloud of pseudo-particles — an ILLUSTRATIVE
// visualisation of the computed drift and its uncertainty envelope, not extra
// model data. The cloud is deterministic (seeded PRNG), anchored to the
// backend trajectory, and scaled to the backend envelopes, so it never shows
// anything the model did not compute.

const KM_PER_DEG_LAT = 111.32;

// Deterministic PRNG (mulberry32) so replays look identical.
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashSeed(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// Approximate gaussian from PRNG (Box–Muller).
function gauss(rnd) {
  const u = Math.max(rnd(), 1e-9), v = rnd();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// Representative radius (km) of a polygon envelope around its centroid.
export function envelopeRadiusKm(geometry, fallbackKm = 1.5) {
  if (!geometry) return fallbackKm;
  const rings =
    geometry.type === "Polygon" ? [geometry.coordinates[0]] :
    geometry.type === "MultiPolygon" ? geometry.coordinates.map((p) => p[0]) : [];
  const pts = rings.flat();
  if (pts.length < 3) return fallbackKm;
  let cx = 0, cy = 0;
  for (const [lon, lat] of pts) { cx += lon; cy += lat; }
  cx /= pts.length; cy /= pts.length;
  const kmLon = KM_PER_DEG_LAT * Math.cos((cy * Math.PI) / 180);
  let sum = 0;
  for (const [lon, lat] of pts) {
    const dx = (lon - cx) * kmLon, dy = (lat - cy) * KM_PER_DEG_LAT;
    sum += Math.sqrt(dx * dx + dy * dy);
  }
  return Math.max(0.2, (sum / pts.length) * 0.9);
}

// Build a particle cloud bound to a backend trajectory.
//   points        [[lat, lon], ...]   (backend trajectory, any order)
//   timesUtc      ISO strings aligned 1:1 with points
//   startSpreadKm cloud radius at the earliest timestamp
//   endSpreadKm   cloud radius at the latest timestamp
export function buildCloud({ points, timesUtc, count, startSpreadKm, endSpreadKm, seed }) {
  if (!points?.length || !timesUtc?.length) return null;
  const n = Math.min(points.length, timesUtc.length);
  const samples = [];
  for (let i = 0; i < n; i++)
    samples.push({ t: new Date(timesUtc[i]).getTime(), lat: points[i][0], lon: points[i][1] });
  samples.sort((a, b) => a.t - b.t);

  const rnd = mulberry32(hashSeed(seed));
  const parts = new Float32Array(count * 4); // ang, radial(|gauss|), lagJitter, wobblePhase
  for (let i = 0; i < count; i++) {
    parts[i * 4] = rnd() * Math.PI * 2;
    parts[i * 4 + 1] = Math.min(2.6, Math.abs(gauss(rnd))) * 0.55;
    parts[i * 4 + 2] = (rnd() - 0.5) * 0.10;
    parts[i * 4 + 3] = rnd() * Math.PI * 2;
  }
  return { samples, parts, count, startSpreadKm, endSpreadKm,
    t0: samples[0].t, t1: samples[samples.length - 1].t };
}

// Centroid position at time t (piecewise-linear over backend timestamps).
function centroidAt(samples, t) {
  if (t <= samples[0].t) return samples[0];
  const last = samples[samples.length - 1];
  if (t >= last.t) return last;
  let i = 1;
  while (samples[i].t < t) i++;
  const a = samples[i - 1], b = samples[i];
  const f = b.t === a.t ? 0 : (t - a.t) / (b.t - a.t);
  return { lat: a.lat + (b.lat - a.lat) * f, lon: a.lon + (b.lon - a.lon) * f };
}

// Particle [lat, lon] pairs at time t → flat Float64Array [lat0, lon0, ...].
export function cloudPositions(cloud, tMs, out) {
  const { samples, parts, count, startSpreadKm, endSpreadKm, t0, t1 } = cloud;
  const span = Math.max(1, t1 - t0);
  const res = out && out.length === count * 2 ? out : new Float64Array(count * 2);
  const pGlobal = Math.min(1, Math.max(0, (tMs - t0) / span));
  for (let i = 0; i < count; i++) {
    const ang = parts[i * 4], rad = parts[i * 4 + 1],
      lag = parts[i * 4 + 2], ph = parts[i * 4 + 3];
    const p = Math.min(1, Math.max(0, pGlobal + lag * pGlobal * (1 - pGlobal) * 4));
    const c = centroidAt(samples, t0 + p * span);
    // diffusive growth of the cloud radius between the two backend envelopes
    const spread = startSpreadKm + (endSpreadKm - startSpreadKm) * Math.sqrt(pGlobal);
    const wob = 1 + 0.16 * Math.sin(ph + pGlobal * 5.2);
    const rKm = rad * spread * wob;
    const kmLon = KM_PER_DEG_LAT * Math.cos((c.lat * Math.PI) / 180);
    res[i * 2] = c.lat + (Math.sin(ang) * rKm) / KM_PER_DEG_LAT;
    res[i * 2 + 1] = c.lon + (Math.cos(ang) * rKm) / kmLon;
  }
  return res;
}
