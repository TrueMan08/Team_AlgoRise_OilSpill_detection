import { useCallback, useEffect, useMemo, useRef } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import { buildCloud, cloudPositions, buildPolygonCloud, polygonCloudPositions, centroidAt, envelopeRadiusKm } from "../Simulation/particles";

// Deterministic visualization of the BACKEND drift results. The overlay owns
// no clock and no physics: particle positions are pure functions of the
// master UTC clock evaluated against the backend trajectory timestamps.
//
//   HINDCAST stage — a coherent cloud whose position at time T is the
//     backend backward trajectory's position at that ACTUAL timestamp.
//     The clock plays BACKWARD (12:00 → 06:00), so the cloud starts over
//     the observed slick and converges onto the probable source region.
//     Timestamps are never reversed or re-scaled.
//
//   FORWARD stage — oil appears at the backend release time/location and
//     follows the /forward trajectory to the predicted footprint.
//
// The trail drawn here is the single representative backend trajectory —
// no duplicate polylines elsewhere.

const RELEASE_PULSE_SIM_MS = 8 * 60 * 1000;

export default function DriftCloudOverlay({
  hindcast,
  forward,
  slickGeometry,
  stage = 0,
  timeMs,
}) {
  const map = useMap();
  const canvasRef = useRef(null);
  const originRef = useRef(null);
  const backBufRef = useRef(null);
  const fwdBufRef = useRef(null);

  /* ── Clouds straight from backend outputs (no time reinterpretation) ── */

  const backCloud = useMemo(() => {
    if (!hindcast?.backward_trajectory || !hindcast?.trajectory_timestamps_utc?.length)
      return null;
    const points = (hindcast.backward_trajectory.coordinates || []).map(
      ([lon, lat]) => [lat, lon]
    );
    const region = hindcast.source_region?.candidate_regions?.[0];
    // Structure-preserving cloud: its particles are sampled inside the
    // OBSERVED detection polygon, so the first hindcast frame (12:00 UTC)
    // coincides exactly with the observed footprint. Each trajectory point
    // keeps ITS backend timestamp — position(06:00)=source end,
    // position(12:00)=slick end — and the whole body translates coherently,
    // easing toward the source-region envelope at the earliest time.
    return buildPolygonCloud({
      points,
      timesUtc: hindcast.trajectory_timestamps_utc,
      geometry: slickGeometry,
      count: 620,
      endSpreadKm: envelopeRadiusKm(region?.geometry, 2.5),
      seed: "oiltrace-back",
    });
  }, [hindcast, slickGeometry]);

  const fwdCloud = useMemo(() => {
    if (!forward?.trajectory || !forward?.trajectory_timestamps_utc?.length) return null;
    const points = (forward.trajectory.coordinates || []).map(([lon, lat]) => [lat, lon]);
    return buildCloud({
      points,
      timesUtc: forward.trajectory_timestamps_utc,
      // Deliberately sparse: particles are staggered along the travelled
      // path (each has its own alongT), so a modest count reads as a
      // narrow-at-release, widening-downstream plume rather than a blob.
      count: 180,
      startSpreadKm: 0.12,
      endSpreadKm: Math.min(
        2.2,
        envelopeRadiusKm(forward.predicted_footprint || slickGeometry, 1.6)
      ),
      seed: "oiltrace-fwd",
    });
  }, [forward, slickGeometry]);

  const releaseLatLng = useMemo(() => {
    const loc = forward?.release_location;
    if (!loc) return null;
    return [+loc.lat, +loc.lon];
  }, [forward]);

  /* ── Drawing ─────────────────────────────────────────────────────── */

  const stateRef = useRef({});
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const origin = originRef.current;
    if (!canvas || !origin) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.width / dpr, h = canvas.height / dpr;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const { backCloud: bc, fwdCloud: fc, releaseLatLng: rel, timeMs: t, stage: st } =
      stateRef.current;
    if (!bc && !fc) return;
    const zoom = map.getZoom();
    const r = Math.max(1.05, Math.min(2.8, 1.15 * Math.pow(1.12, 10.5 - zoom)));

    const toXY = ([lat, lon]) => {
      const point = map.latLngToLayerPoint([lat, lon]);
      return { x: point.x - origin.x, y: point.y - origin.y };
    };

    const drawArrowHead = (a, b, color) => {
      const dx = b.x - a.x, dy = b.y - a.y;
      const len = Math.hypot(dx, dy);
      if (len < 6) return;
      const ux = dx / len, uy = dy / len;
      const size = 7;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(b.x - size * (ux * 0.87 - uy * 0.5), b.y - size * (uy * 0.87 + ux * 0.5));
      ctx.lineTo(b.x, b.y);
      ctx.lineTo(b.x - size * (ux * 0.87 + uy * 0.5), b.y - size * (uy * 0.87 - ux * 0.5));
      ctx.stroke();
    };

    const drawLabel = (tip, text, color, side = "right") => {
      ctx.font = "700 11px Inter, system-ui, sans-serif";
      const tw = ctx.measureText(text).width;
      const pad = 7, ch = 20;
      let x = side === "right" ? tip.x + 12 : tip.x - tw - pad * 2 - 12;
      let y = side === "right" ? tip.y - ch - 10 : tip.y + 14;
      x = Math.max(4, Math.min(x, w - tw - pad * 2 - 4));
      y = Math.max(4, Math.min(y, h - ch - 4));
      ctx.beginPath();
      ctx.roundRect(x, y, tw + pad * 2, ch, 6);
      ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.fillText(text, x + pad, y + 14);
    };

    // The travelled portion of the backend trajectory at real time `now`.
    //   forward:  from t0 up to now — arrows point with increasing time.
    //   backward: from t1 (slick) down to now — arrows point with
    //             DECREASING time, i.e. toward the probable source.
    const travelledPath = (cloud, now, direction) => {
      const clamped = Math.min(cloud.t1, Math.max(cloud.t0, now));
      const cur = centroidAt(cloud.samples, clamped);
      const pts = [];
      if (direction === "forward") {
        for (const s of cloud.samples) if (s.t <= clamped) pts.push([s.lat, s.lon]);
        pts.push([cur.lat, cur.lon]);
      } else {
        for (let i = cloud.samples.length - 1; i >= 0; i--) {
          const s = cloud.samples[i];
          if (s.t >= clamped) pts.push([s.lat, s.lon]);
        }
        pts.push([cur.lat, cur.lon]);
      }
      return pts;
    };

    const drawCloud = (cloud, now, direction, fill, trailStroke, bufRef, label, side, dotScale = 1.35) => {
      const pos =
        cloud.kind === "polygon"
          ? polygonCloudPositions(cloud, now, bufRef.current)
          : cloudPositions(cloud, now, bufRef.current);
      bufRef.current = pos;
      const trail = travelledPath(cloud, now, direction);
      if (trail.length >= 2) {
        ctx.beginPath();
        trail.forEach((pair, index) => {
          const { x, y } = toXY(pair);
          if (index === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.strokeStyle = trailStroke;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }
      ctx.fillStyle = fill;
      const cr = r * dotScale;
      for (let i = 0; i < cloud.count; i += 1) {
        const lat = pos[i * 2];
        const lng = pos[i * 2 + 1];
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
        const point = map.latLngToLayerPoint([lat, lng]);
        const x = point.x - origin.x;
        const y = point.y - origin.y;
        if (x < -cr || y < -cr || x > w + cr || y > h + cr) continue;
        ctx.beginPath();
        ctx.arc(x, y, cr, 0, Math.PI * 2);
        ctx.fill();
      }
      if (trail.length >= 2) {
        const solid = fill.replace(/[\d.]+\)$/, "0.95)");
        const step = Math.max(3, Math.floor(trail.length / 4));
        for (let i = step; i < trail.length; i += step) {
          drawArrowHead(toXY(trail[i - 1]), toXY(trail[i]), solid);
        }
        const tip = toXY(trail[trail.length - 1]);
        drawArrowHead(toXY(trail[trail.length - 2]), tip, solid);
        // Anchor ring at the origin end of the travelled path. The physical
        // displacement here is genuinely small (a few km against a slick
        // over ten km wide), so mark both ends rather than exaggerate the
        // motion: the ring is where the cloud began, the tip is where the
        // clock has taken it.
        const anchor = toXY(trail[0]);
        ctx.strokeStyle = solid;
        ctx.lineWidth = 1.4;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.arc(anchor.x, anchor.y, 5.5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        if (label) drawLabel(tip, label, solid, side);
      }
    };

    // Stage-scoped: exactly one reconstruction on screen at a time.
    if (st === 1 && bc) {
      drawCloud(
        bc, Number.isFinite(t) ? t : bc.t1, "backward",
        "rgba(13, 121, 140, 0.88)", "rgba(13, 148, 172, 0.65)", backBufRef,
        "HINDCAST RECONSTRUCTION · to probable source", "left"
      );
    } else if (st === 3 && fc) {
      const now = Number.isFinite(t) ? t : fc.t0;
      if (now >= fc.t0) {
        drawCloud(
          fc, now, "forward",
          "rgba(21, 128, 61, 0.86)", "rgba(34, 197, 94, 0.6)", fwdBufRef,
          "FORWARD DRIFT · release → slick", "right", 1.15
        );
        if (rel && now - fc.t0 <= RELEASE_PULSE_SIM_MS) {
          const f = (now - fc.t0) / RELEASE_PULSE_SIM_MS;
          const p = map.latLngToLayerPoint(rel);
          ctx.strokeStyle = `rgba(180, 83, 9, ${(1 - f) * 0.7})`;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(p.x - origin.x, p.y - origin.y, 8 + f * 28, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
    }
  }, [map]);

  const drawRef = useRef(draw);

  useEffect(() => {
    stateRef.current = { backCloud, fwdCloud, releaseLatLng, timeMs, stage };
    drawRef.current = draw;
    drawRef.current();
  }, [timeMs, stage, backCloud, fwdCloud, releaseLatLng, draw]);

  /* ── Canvas lifecycle in the overlay pane ────────────────────────── */

  useEffect(() => {
    const canvas = L.DomUtil.create("canvas", "leaflet-zoom-animated");
    canvas.style.pointerEvents = "none";
    map.getPanes().overlayPane.appendChild(canvas);
    canvasRef.current = canvas;

    const reset = () => {
      const topLeft = map.containerPointToLayerPoint([0, 0]);
      L.DomUtil.setPosition(canvas, topLeft);
      originRef.current = topLeft;
      const size = map.getSize(), dpr = window.devicePixelRatio || 1;
      if (canvas.width !== size.x * dpr || canvas.height !== size.y * dpr) {
        canvas.width = size.x * dpr;
        canvas.height = size.y * dpr;
        canvas.style.width = `${size.x}px`;
        canvas.style.height = `${size.y}px`;
      }
      drawRef.current();
    };
    const animateZoom = (e) => {
      const scale = map.getZoomScale(e.zoom);
      const offset = map
        ._getCenterOffset(e.center)
        ._multiplyBy(-scale)
        .subtract(map._getMapPanePos());
      L.DomUtil.setTransform(canvas, offset, scale);
    };
    map.on("move moveend zoomend viewreset resize", reset);
    if (map.options.zoomAnimation && L.Browser.any3d) map.on("zoomanim", animateZoom);
    reset();
    return () => {
      map.off("move moveend zoomend viewreset resize", reset);
      map.off("zoomanim", animateZoom);
      L.DomUtil.remove(canvas);
      canvasRef.current = null;
    };
  }, [map]);

  return null;
}
