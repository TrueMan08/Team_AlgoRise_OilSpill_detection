const POINTS = [
  "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
];

export function compassLabel(degrees) {
  const deg = Number(degrees);
  if (!Number.isFinite(deg)) return "—";
  const idx = Math.round((((deg % 360) + 360) % 360) / 22.5) % 16;
  return POINTS[idx];
}

export function msToKnots(metersPerSecond) {
  const n = Number(metersPerSecond);
  return Number.isFinite(n) ? n * 1.94384 : 0;
}
