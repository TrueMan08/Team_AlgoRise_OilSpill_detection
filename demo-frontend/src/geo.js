// Geometry helpers. GeoJSON coordinates are [longitude, latitude];
// Leaflet wants [latitude, longitude]. All conversions live here.

export function ringToLatLngs(ring) {
  return ring.map(([lon, lat]) => [lat, lon]);
}

export function polygonToLatLngs(geometry) {
  if (!geometry) return [];
  if (geometry.type === "Polygon") return geometry.coordinates.map(ringToLatLngs);
  if (geometry.type === "MultiPolygon")
    return geometry.coordinates.map((poly) => poly.map(ringToLatLngs));
  return [];
}

export function lineToLatLngs(geometry) {
  if (!geometry || geometry.type !== "LineString") return [];
  return geometry.coordinates.map(([lon, lat]) => [lat, lon]);
}

function collectPositions(geometry, out) {
  if (!geometry) return;
  const { type, coordinates } = geometry;
  if (type === "Polygon") coordinates.forEach((r) => r.forEach((c) => out.push(c)));
  else if (type === "MultiPolygon")
    coordinates.forEach((p) => p.forEach((r) => r.forEach((c) => out.push(c))));
  else if (type === "LineString") coordinates.forEach((c) => out.push(c));
}

// Bounds of one or more geometries → { minLon, minLat, maxLon, maxLat }
export function geomBounds(geometries) {
  const pts = [];
  geometries.filter(Boolean).forEach((g) => collectPositions(g, pts));
  if (!pts.length) return null;
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
  for (const [lon, lat] of pts) {
    if (lon < minLon) minLon = lon;
    if (lat < minLat) minLat = lat;
    if (lon > maxLon) maxLon = lon;
    if (lat > maxLat) maxLat = lat;
  }
  return { minLon, minLat, maxLon, maxLat };
}

// bbox string "min_lon,min_lat,max_lon,max_lat" expanded by a degree buffer.
export function bboxString(bounds, bufferDeg = 0.6) {
  const f = (n) => n.toFixed(4);
  return [
    f(bounds.minLon - bufferDeg),
    f(bounds.minLat - bufferDeg),
    f(bounds.maxLon + bufferDeg),
    f(bounds.maxLat + bufferDeg),
  ].join(",");
}

export function boundsToLeaflet(bounds, padDeg = 0.15) {
  return [
    [bounds.minLat - padDeg, bounds.minLon - padDeg],
    [bounds.maxLat + padDeg, bounds.maxLon + padDeg],
  ];
}

export function shiftIso(iso, hours) {
  return new Date(new Date(iso).getTime() + hours * 3600 * 1000).toISOString();
}

export function fmtUtc(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getUTCDate()} ${["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getUTCMonth()]} ${d.getUTCFullYear()} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
}

export function fmtClock(iso) {
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}
