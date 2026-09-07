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
export function buildCloud({ points, timesUtc, count, startSpreadKm, endSpreadKm, seed, preformed = false }) {
  if (!points?.length || !timesUtc?.length) return null;
  const n = Math.min(points.length, timesUtc.length);
  const samples = [];
  for (let i = 0; i < n; i++)
    samples.push({ t: new Date(timesUtc[i]).getTime(), lat: points[i][0], lon: points[i][1] });
  samples.sort((a, b) => a.t - b.t);

  const rnd = mulberry32(hashSeed(seed));
  const parts = new Float32Array(count * 4); // ang, radial, birthFrac, wobblePhase
  for (let i = 0; i < count; i++) {
    parts[i * 4] = rnd() * Math.PI * 2;
    parts[i * 4 + 1] = Math.min(1.8, Math.abs(gauss(rnd))) * 0.42;
    parts[i * 4 + 2] = Math.pow(rnd(), 0.72) * 0.62;
    parts[i * 4 + 3] = rnd() * Math.PI * 2;
  }
  return {
    samples,
    parts,
    count,
    // Trust the caller's envelopes: they come from the backend geometries
    // (observed slick, source region, predicted footprint). The old hard
    // clamps (0.35 / 2.4 km) shrank a cloud meant to cover a ~10 km slick
    // into a single dot — the "one blue point" failure mode.
    startSpreadKm: Math.min(15, Math.max(0.05, Number(startSpreadKm) || 0.2)),
    endSpreadKm: Math.min(15, Math.max(0.05, Number(endSpreadKm) || 1.4)),
    // preformed: the oil mass already exists in full at t0 (a detected
    // slick being traced), so every particle is alive from the first frame
    // and the cloud travels as one coherent body along the trajectory.
    preformed: Boolean(preformed),
    t0: samples[0].t,
    t1: samples[samples.length - 1].t,
  };
}

// Centroid position at time t (piecewise-linear over backend timestamps).
export function centroidAt(samples, t) {
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
  const { samples, parts, count, startSpreadKm, endSpreadKm, t0, t1, preformed } = cloud;
  const span = Math.max(1, t1 - t0);
  const res = out && out.length === count * 2 ? out : new Float64Array(count * 2);
  const now = Number.isFinite(tMs) ? tMs : t0;
  for (let i = 0; i < count; i++) {
    const ang = parts[i * 4];
    const rad = parts[i * 4 + 1];
    const birthFrac = parts[i * 4 + 2];
    const ph = parts[i * 4 + 3];
    const birthT = preformed ? t0 : t0 + birthFrac * span;
    if (now < birthT) {
      res[i * 2] = Number.NaN;
      res[i * 2 + 1] = Number.NaN;
      continue;
    }
    // preformed: the whole mass rides the trajectory together at the ACTUAL
    // clock time — no per-particle lag, no wobble, no birth animation. The
    // clock may run in either direction; position and spread are pure
    // functions of the timestamp, so backward playback needs no time tricks.
    const alongT = preformed
      ? Math.min(t1, Math.max(t0, now))
      : t0 + birthFrac * Math.max(0, now - t0);
    const c = centroidAt(samples, alongT);
    const frac = Math.max(0, Math.min(1, (alongT - t0) / span));
    const spread = preformed
      ? startSpreadKm + (endSpreadKm - startSpreadKm) * frac
      : startSpreadKm + (endSpreadKm - startSpreadKm) * Math.sqrt(Math.max(0, Math.min(1, (now - birthT) / span)));
    const wob = preformed ? 1 : 1 + 0.12 * Math.sin(ph + ((now - birthT) / span) * 6.2);
    const rKm = rad * spread * wob;
    const kmLon = KM_PER_DEG_LAT * Math.cos((c.lat * Math.PI) / 180);
    res[i * 2] = c.lat + (Math.sin(ang) * rKm) / KM_PER_DEG_LAT;
    res[i * 2 + 1] = c.lon + (Math.cos(ang) * rKm) / kmLon;
  }
  return res;
}

export function overlayFrameFromCloud(cloud, tMs) {
  if (!cloud?.samples?.length) return { particles: [], trails: [], flowLines: [] };
  const now = Number.isFinite(tMs)
    ? Math.min(cloud.t1, Math.max(cloud.t0, tMs))
    : cloud.t0;

  const positions = cloudPositions(cloud, now);
  const particles = [];

  for (let i = 0; i < cloud.count; i += 1) {
    const pLat = positions[i * 2];
    const pLon = positions[i * 2 + 1];
    if (!Number.isFinite(pLat) || !Number.isFinite(pLon)) continue;

    const rad = cloud.parts[i * 4 + 1];
    particles.push({
      id: i,
      latitude: pLat,
      longitude: pLon,
      position: [pLon, pLat],
      radiusPixels: rad < 0.35 ? 1.8 : 1.3,
      category: rad < 0.35 ? "stranded" : rad < 0.7 ? "active" : "initial",
    });
  }

  const trailPath = cloud.samples
    .filter((sample) => sample.t <= now + 1000)
    .map((sample) => [sample.lon, sample.lat]);

  return {
    particles,
    trails: trailPath.length >= 2 ? [{ id: "opendrift-path", path: trailPath }] : [],
    flowLines: [],
  };
}

// Deterministic sample of points STRICTLY INSIDE a GeoJSON polygon —
// the static visual texture of the OBSERVED slick. Seeded PRNG rejection
// sampling: same geometry + seed → identical points, no animation, no
// physics, and no point can fall outside the observation.
export function samplePointsInPolygon(geometry, count, seed = "observed-slick") {
  const ring =
    geometry?.type === "Polygon" ? geometry.coordinates?.[0] :
    geometry?.type === "MultiPolygon" ? geometry.coordinates?.[0]?.[0] : null;
  if (!ring || ring.length < 4) return [];
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
  for (const [lon, lat] of ring) {
    if (lon < minLon) minLon = lon;
    if (lon > maxLon) maxLon = lon;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }
  const inside = (lon, lat) => {
    let odd = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > lat) !== (yj > lat) &&
          lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) odd = !odd;
    }
    return odd;
  };
  const rnd = mulberry32(hashSeed(seed));
  const pts = [];
  let guard = count * 60;
  while (pts.length < count && guard-- > 0) {
    const lon = minLon + rnd() * (maxLon - minLon);
    const lat = minLat + rnd() * (maxLat - minLat);
    if (inside(lon, lat)) pts.push([lat, lon]);
  }
  return pts;
}

// Cloud whose initial shape IS the observed slick polygon.
//
// Particle offsets are sampled deterministically inside the detection
// geometry and expressed relative to its centroid; at time T each particle
// sits at trajectoryPosition(T) + offset × scale(T), where scale eases from
// 1.0 at the slick end of the trajectory to endScale at the source end.
// So the first hindcast frame coincides EXACTLY with the observed footprint,
// and the whole body then translates coherently along the backend
// trajectory while keeping its relative structure. Deterministic; no
// physics; no randomness beyond the seeded sampler.
export function buildPolygonCloud({ points, timesUtc, geometry, count, endSpreadKm, seed }) {
  if (!points?.length || !timesUtc?.length || !geometry) return null;
  const n = Math.min(points.length, timesUtc.length);
  const samples = [];
  for (let i = 0; i < n; i++)
    samples.push({ t: new Date(timesUtc[i]).getTime(), lat: points[i][0], lon: points[i][1] });
  samples.sort((a, b) => a.t - b.t);

  const inPoly = samplePointsInPolygon(geometry, count, seed);
  if (!inPoly.length) return null;
  let cLat = 0, cLon = 0;
  for (const [la, lo] of inPoly) { cLat += la; cLon += lo; }
  cLat /= inPoly.length; cLon /= inPoly.length;
  const kmLon = KM_PER_DEG_LAT * Math.cos((cLat * Math.PI) / 180);
  // offsets in km, preserved for the life of the cloud
  const offsets = new Float64Array(inPoly.length * 2);
  let meanR = 0;
  for (let i = 0; i < inPoly.length; i++) {
    const dyKm = (inPoly[i][0] - cLat) * KM_PER_DEG_LAT;
    const dxKm = (inPoly[i][1] - cLon) * kmLon;
    offsets[i * 2] = dyKm;
    offsets[i * 2 + 1] = dxKm;
    meanR += Math.hypot(dxKm, dyKm);
  }
  meanR = Math.max(0.2, meanR / inPoly.length);
  const endScale = Math.max(0.15, Math.min(3, (Number(endSpreadKm) || meanR) / meanR));
  return {
    kind: "polygon",
    samples,
    offsets,
    count: inPoly.length,
    endScale,
    t0: samples[0].t,
    t1: samples[samples.length - 1].t,
  };
}

// Positions for a polygon cloud at real time t (either clock direction).
export function polygonCloudPositions(cloud, tMs, out) {
  const { samples, offsets, count, endScale, t0, t1 } = cloud;
  const res = out && out.length === count * 2 ? out : new Float64Array(count * 2);
  const now = Math.min(t1, Math.max(t0, Number.isFinite(tMs) ? tMs : t1));
  const c = centroidAt(samples, now);
  // frac 1 at the slick end (t1) → endScale at the source end (t0)
  const frac = (now - t0) / Math.max(1, t1 - t0);
  const scale = endScale + (1 - endScale) * frac;
  const kmLon = KM_PER_DEG_LAT * Math.cos((c.lat * Math.PI) / 180);
  for (let i = 0; i < count; i++) {
    res[i * 2] = c.lat + (offsets[i * 2] * scale) / KM_PER_DEG_LAT;
    res[i * 2 + 1] = c.lon + (offsets[i * 2 + 1] * scale) / kmLon;
  }
  return res;
}
