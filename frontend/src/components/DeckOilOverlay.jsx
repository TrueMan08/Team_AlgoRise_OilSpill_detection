import { useEffect, useMemo, useRef } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import { samplePointsInPolygon } from "../Simulation/particles";
import "./DeckOilOverlay.css";

// PURE OBSERVED-SLICK RENDERER.
//
// This layer draws exactly one thing: a static, petroleum-dark particle
// texture for the OBSERVED SAR slick, sampled deterministically and
// STRICTLY INSIDE the actual detection GeoJSON geometry.
//
// It is an observation, so it never moves, never fades, never recolors,
// never animates, and owns no clock. There is no oil physics here — the
// hindcast/forward reconstructions are a separate overlay driven purely
// by backend trajectories.

const DOT_COUNT = 550;
const DOT_COLOR = "rgba(23, 32, 42, 0.78)";
const CORE_COLOR = "rgba(15, 23, 42, 0.9)";

export default function DeckOilOverlay({ geometry }) {
  const map = useMap();
  const canvasRef = useRef(null);

  // Deterministic sample inside the real observed polygon. Recomputed only
  // when the detection geometry itself changes.
  const dots = useMemo(
    () => (geometry ? samplePointsInPolygon(geometry, DOT_COUNT, "observed-sar-slick") : []),
    [geometry]
  );
  const dotsRef = useRef(dots);
  useEffect(() => {
    dotsRef.current = dots;
  }, [dots]);

  useEffect(() => {
    const canvas = L.DomUtil.create("canvas", "leaflet-zoom-animated");
    canvas.style.pointerEvents = "none";
    map.getPanes().overlayPane.appendChild(canvas);
    canvasRef.current = canvas;

    const redraw = () => {
      const topLeft = map.containerPointToLayerPoint([0, 0]);
      L.DomUtil.setPosition(canvas, topLeft);
      const size = map.getSize();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      if (canvas.width !== size.x * dpr || canvas.height !== size.y * dpr) {
        canvas.width = size.x * dpr;
        canvas.height = size.y * dpr;
        canvas.style.width = `${size.x}px`;
        canvas.style.height = `${size.y}px`;
      }
      const ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size.x, size.y);

      const pts = dotsRef.current;
      if (!pts.length) return;
      const zoom = map.getZoom();
      const r = Math.max(0.9, Math.min(2.4, 1.05 * Math.pow(1.12, 10.5 - zoom)));
      for (let i = 0; i < pts.length; i++) {
        const p = map.latLngToLayerPoint(pts[i]);
        const x = p.x - topLeft.x;
        const y = p.y - topLeft.y;
        if (x < -4 || y < -4 || x > size.x + 4 || y > size.y + 4) continue;
        ctx.beginPath();
        // Every third dot slightly darker/larger: reads as thicker oil
        // without implying any structure the SAR product did not observe.
        ctx.fillStyle = i % 3 === 0 ? CORE_COLOR : DOT_COLOR;
        ctx.arc(x, y, i % 3 === 0 ? r * 1.25 : r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    map.on("move moveend zoomend viewreset resize", redraw);
    redraw();
    return () => {
      map.off("move moveend zoomend viewreset resize", redraw);
      L.DomUtil.remove(canvas);
      canvasRef.current = null;
    };
  }, [map]);

  // Repaint when the geometry (and therefore the sample) changes.
  useEffect(() => {
    map.fire("viewreset");
  }, [dots, map]);

  return null;
}
