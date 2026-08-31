import { useEffect, useRef } from "react";
import L from "leaflet";
import { polygonToLatLngs, lineToLatLngs, geomBounds, boundsToLeaflet, fmtUtc } from "../geo.js";
import { buildCloud, cloudPositions, envelopeRadiusKm } from "../particles.js";
import { SAR_CREDIT } from "../demo.js";

const COL = {
  slick: "#e8862e", source: "#3b76d2", backTraj: "#1899b8",
  vessel: "#7a8ea1", selected: "#d92f23", fwd: "#7a3fd1", foot: "#17a08b",
};

// Top-view ship silhouette, rotated to the vessel's course-over-ground.
function shipIcon(color, selected, cog = 0) {
  const s = selected ? 34 : 27;
  return L.divIcon({
    className: "vessel-div-icon",
    iconSize: [s, s],
    iconAnchor: [s / 2, s / 2],
    html: `<div style="width:${s}px;height:${s}px;transform:rotate(${Number(cog) || 0}deg);filter:drop-shadow(0 1px 2px rgba(8,20,34,0.45));">
      <svg width="${s}" height="${s}" viewBox="0 0 24 24">
        <path d="M12 1.6 C14.6 4.4 16.4 6.6 16.4 9.2 L16.4 19.6 Q16.4 21.6 14.4 21.9 L9.6 21.9 Q7.6 21.6 7.6 19.6 L7.6 9.2 C7.6 6.6 9.4 4.4 12 1.6 Z"
          fill="${color}" stroke="#ffffff" stroke-width="1.5" stroke-linejoin="round"/>
        <rect x="9.4" y="12.6" width="5.2" height="6.4" rx="1" fill="rgba(255,255,255,0.75)"/>
        <line x1="9.4" y1="10" x2="14.6" y2="10" stroke="rgba(255,255,255,0.7)" stroke-width="1.1"/>
      </svg></div>`,
  });
}

// Canvas layer that lives in the map's overlay pane, so it pans for free with
// the map and scales via CSS during animated zooms (Leaflet.heat technique) —
// no lag between the basemap and the particle cloud.
const ParticleCanvasLayer = L.Layer.extend({
  initialize(draw) { this._drawCb = draw; },
  onAdd(map) {
    this._map = map;
    const c = (this._canvas = L.DomUtil.create("canvas", "leaflet-zoom-animated"));
    c.style.pointerEvents = "none";
    map.getPanes().overlayPane.appendChild(c);
    map.on("moveend zoomend viewreset resize", this._reset, this);
    if (map.options.zoomAnimation && L.Browser.any3d) map.on("zoomanim", this._animateZoom, this);
    this._reset();
    return this;
  },
  onRemove(map) {
    L.DomUtil.remove(this._canvas);
    map.off("moveend zoomend viewreset resize", this._reset, this);
    map.off("zoomanim", this._animateZoom, this);
  },
  _animateZoom(e) {
    const scale = this._map.getZoomScale(e.zoom);
    const offset = this._map._getCenterOffset(e.center)._multiplyBy(-scale)
      .subtract(this._map._getMapPanePos());
    L.DomUtil.setTransform(this._canvas, offset, scale);
  },
  _reset() {
    const topLeft = this._map.containerPointToLayerPoint([0, 0]);
    L.DomUtil.setPosition(this._canvas, topLeft);
    this._origin = topLeft;
    const size = this._map.getSize(), dpr = window.devicePixelRatio || 1;
    if (this._canvas.width !== size.x * dpr || this._canvas.height !== size.y * dpr) {
      this._canvas.width = size.x * dpr;
      this._canvas.height = size.y * dpr;
      this._canvas.style.width = `${size.x}px`;
      this._canvas.style.height = `${size.y}px`;
    }
    this.redraw();
  },
  redraw() { if (this._map) this._drawCb(this); },
});

function releaseIcon() {
  return L.divIcon({
    className: "vessel-div-icon",
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    html: `<svg width="34" height="34" viewBox="0 0 34 34">
      <circle cx="17" cy="17" r="14" fill="none" stroke="#d92f23" stroke-width="2.5" stroke-dasharray="4 3"/>
      <circle cx="17" cy="17" r="5.5" fill="#d92f23" stroke="#fff" stroke-width="2"/>
    </svg>`,
  });
}

function driftDot() {
  return L.divIcon({
    className: "vessel-div-icon",
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    html: `<svg width="18" height="18" viewBox="0 0 18 18">
      <circle cx="9" cy="9" r="7" fill="#7a3fd1" stroke="#fff" stroke-width="2.5"/>
    </svg>`,
  });
}

export default function MapView({ inv, layers, selectedMmsi, onSelectVessel, timeT, onOpenSar }) {
  const mapRef = useRef(null);
  const groupsRef = useRef({});
  const driftMarkerRef = useRef(null);
  const fittedRef = useRef("");
  const particleLayerRef = useRef(null);
  const cloudsRef = useRef({ back: null, fwd: null });
  const drawStateRef = useRef({ timeT: null, show: true, hasFwd: false });
  const posBufRef = useRef(null);

  // ---- particle cloud renderer (OpenDrift-style dots) -------------------
  const drawParticles = (layer) => {
    const map = mapRef.current;
    if (!map || !layer?._canvas || !layer._origin) return;
    const dpr = window.devicePixelRatio || 1;
    const canvas = layer._canvas;
    const w = canvas.width / dpr, h = canvas.height / dpr;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const st = drawStateRef.current;
    if (!st.show) return;
    const cloud = st.hasFwd ? cloudsRef.current.fwd : cloudsRef.current.back;
    if (!cloud) return;
    const tMs = st.timeT ? new Date(st.timeT).getTime() : cloud.t1;
    const pos = cloudPositions(cloud, tMs, posBufRef.current);
    posBufRef.current = pos;
    ctx.fillStyle = st.hasFwd ? "rgba(16,20,26,0.62)" : "rgba(10,96,122,0.55)";
    const r = map.getZoom() >= 10 ? 1.9 : 1.5;
    const o = layer._origin;
    for (let i = 0; i < cloud.count; i++) {
      const p = map.latLngToLayerPoint([pos[i * 2], pos[i * 2 + 1]]);
      const x = p.x - o.x, y = p.y - o.y;
      if (x < -8 || y < -8 || x > w + 8 || y > h + 8) continue;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 6.2832);
      ctx.fill();
    }
  };
  const drawRef = useRef(drawParticles);
  drawRef.current = drawParticles;
  const redrawParticles = () => particleLayerRef.current?.redraw();

  // ---- init once --------------------------------------------------------
  useEffect(() => {
    const map = L.map("oiltrace-map", { zoomControl: false, attributionControl: true, maxZoom: 13, minZoom: 4 });
    map.setView([60.0, 4.6], 8);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}", {
      attribution: "Esri, GEBCO, NOAA, Garmin",
      maxZoom: 13, maxNativeZoom: 10,
    }).addTo(map);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 13, maxNativeZoom: 10, opacity: 0.85,
    }).addTo(map);
    L.control.zoom({ position: "topright" }).addTo(map);
    L.control.scale({ imperial: false, position: "bottomright" }).addTo(map);
    mapRef.current = map;
    const g = {};
    for (const k of ["slick", "source", "backTraj", "vessels", "release", "fwdTraj", "footprint"])
      g[k] = L.layerGroup().addTo(map);
    groupsRef.current = g;
    particleLayerRef.current = new ParticleCanvasLayer((layer) => drawRef.current(layer)).addTo(map);
    return () => { particleLayerRef.current = null; map.remove(); };
  }, []);

  // ---- (re)build particle clouds from backend outputs -------------------
  useEffect(() => {
    const seedBase = inv.incident_id || "oiltrace";
    let back = null, fwd = null;
    if (inv.hindcast?.backward_trajectory && inv.hindcast.trajectory_timestamps_utc?.length) {
      const region = inv.hindcast.source_region.candidate_regions[0];
      back = buildCloud({
        points: lineToLatLngs(inv.hindcast.backward_trajectory),
        timesUtc: inv.hindcast.trajectory_timestamps_utc,
        count: 900,
        startSpreadKm: envelopeRadiusKm(region?.geometry, 2.5),
        endSpreadKm: envelopeRadiusKm(inv.slick?.geometry, 1.8),
        seed: `${seedBase}-back`,
      });
    }
    if (inv.forward?.trajectory && inv.forward.trajectory_timestamps_utc?.length) {
      fwd = buildCloud({
        points: lineToLatLngs(inv.forward.trajectory),
        timesUtc: inv.forward.trajectory_timestamps_utc,
        count: 1400,
        startSpreadKm: 0.25,
        endSpreadKm: envelopeRadiusKm(inv.forward.predicted_footprint, 2.0),
        seed: `${seedBase}-fwd`,
      });
    }
    cloudsRef.current = { back, fwd };
    posBufRef.current = null;
    drawStateRef.current.hasFwd = !!fwd;
    redrawParticles();
  }, [inv.hindcast, inv.forward, inv.slick, inv.incident_id]);

  // ---- redraw particles on time / toggle changes ------------------------
  useEffect(() => {
    drawStateRef.current.timeT = timeT;
    drawStateRef.current.show = layers.particles !== false;
    redrawParticles();
  }, [timeT, layers.particles]);

  // ---- rebuild data layers when investigation changes -------------------
  useEffect(() => {
    const map = mapRef.current;
    const g = groupsRef.current;
    if (!map) return;
    Object.values(g).forEach((lg) => lg.clearLayers());
    driftMarkerRef.current = null;

    // Observed slick
    if (inv.slick) {
      const latlngs = polygonToLatLngs(inv.slick.geometry);
      L.polygon(latlngs, {
        color: COL.slick, weight: 2, fillColor: COL.slick, fillOpacity: 0.30,
      }).bindTooltip(
        `<b>Observed slick</b><br/>${fmtUtc(inv.slick.timestamp_utc)}<br/>${inv.slick.area_km2.toFixed(1)} km² · conf ${inv.slick.confidence.toFixed(2)}`,
        { className: "oiltrace-tip", sticky: true }
      ).addTo(g.slick);
      L.circleMarker([inv.slick.centroid.lat, inv.slick.centroid.lon], {
        radius: 4, color: "#9a5514", fillColor: "#fff", fillOpacity: 1, weight: 2,
      }).addTo(g.slick);
    }

    // Hindcast: source region + backward trajectory
    if (inv.hindcast) {
      for (const c of inv.hindcast.source_region.candidate_regions) {
        L.polygon(polygonToLatLngs(c.geometry), {
          color: COL.source, weight: 1.5, dashArray: "5 4",
          fillColor: COL.source, fillOpacity: 0.22,
        }).bindTooltip(
          `<b>Probable source region</b><br/>window ${fmtUtc(c.start_time_utc)} → ${fmtUtc(c.end_time_utc)}<br/>source-region probability mass: ${(c.probability * 100).toFixed(0)}%`,
          { className: "oiltrace-tip", sticky: true }
        ).addTo(g.source);
        if (c.centroid)
          L.circleMarker([c.centroid.lat, c.centroid.lon], {
            radius: 5, color: COL.source, fillColor: "#fff", fillOpacity: 1, weight: 2.5,
          }).addTo(g.source);
      }
      const bt = lineToLatLngs(inv.hindcast.backward_trajectory);
      if (bt.length) {
        L.polyline(bt, { color: COL.backTraj, weight: 2.5, dashArray: "7 6", opacity: 0.9 }).addTo(g.backTraj);
        bt.forEach((p, i) => {
          if (i % 2 === 0)
            L.circleMarker(p, { radius: 2.5, color: COL.backTraj, fillColor: COL.backTraj, fillOpacity: 1, weight: 0 }).addTo(g.backTraj);
        });
      }
    }

    // Vessels
    if (inv.vessels) {
      for (const v of inv.vessels) {
        const isSel = v.mmsi === selectedMmsi;
        const track = lineToLatLngs(v.track_geometry);
        const color = isSel ? COL.selected : COL.vessel;
        if (track.length)
          L.polyline(track, { color, weight: isSel ? 3 : 2, opacity: isSel ? 0.95 : 0.65 })
            .on("click", () => onSelectVessel(v.mmsi)).addTo(g.vessels);
        const last = v.track_points[v.track_points.length - 1];
        L.marker([last.position.lat, last.position.lon], { icon: shipIcon(color, isSel, last.cog) })
          .bindTooltip(
            `<b>${v.name || "Unknown vessel"}</b><br/>MMSI ${v.mmsi} · ${v.vessel_type || "—"}<br/>${v.track_points.length} AIS points${v.ais_gaps?.length ? ` · ${v.ais_gaps.length} gap(s)` : ""}`,
            { className: "oiltrace-tip" }
          )
          .on("click", () => onSelectVessel(v.mmsi)).addTo(g.vessels);
      }
    }

    // Estimated release point (from attribution's selected candidate / forward run)
    const rel = inv.forward
      ? { loc: inv.forward.release_location, t: inv.forward.release_time_utc }
      : inv.attribution?.top_candidates?.length
        ? (() => {
            const c = inv.attribution.top_candidates.find((x) => x.vessel_mmsi === selectedMmsi)
              || inv.attribution.top_candidates[0];
            return { loc: c.release_location, t: c.release_time_utc };
          })()
        : null;
    if (rel) {
      L.marker([rel.loc.lat, rel.loc.lon], { icon: releaseIcon() })
        .bindTooltip(
          `<b>Estimated release</b><br/>${fmtUtc(rel.t)}`,
          { className: "oiltrace-tip", permanent: true, direction: "right", offset: [18, 0] }
        ).addTo(g.release);
    }

    // Forward simulation: trajectory + predicted footprint + drift marker
    if (inv.forward) {
      const ft = lineToLatLngs(inv.forward.trajectory);
      if (ft.length)
        L.polyline(ft, { color: COL.fwd, weight: 2.5, dashArray: "2 7", opacity: 0.95 }).addTo(g.fwdTraj);
      if (inv.forward.predicted_footprint)
        L.polygon(polygonToLatLngs(inv.forward.predicted_footprint), {
          color: COL.foot, weight: 2, fillColor: COL.foot, fillOpacity: 0.20,
        }).bindTooltip("<b>Predicted footprint</b><br/>simulated particle envelope — not an observed slick",
          { className: "oiltrace-tip", sticky: true }).addTo(g.footprint);
      if (ft.length) {
        driftMarkerRef.current = L.marker(ft[0], { icon: driftDot() }).addTo(g.fwdTraj);
      }
    }

    // ---- fit bounds on stage transitions --------------------------------
    const stageKey = [!!inv.slick, !!inv.hindcast, !!inv.vessels, !!inv.forward].join("");
    if (stageKey !== fittedRef.current) {
      fittedRef.current = stageKey;
      const geoms = [inv.slick?.geometry];
      if (inv.forward) {
        // Forward/counterfactual stages: zoom to the simulated release story,
        // not the full extent of every vessel track.
        geoms.push(inv.forward.trajectory);
        if (inv.forward.predicted_footprint) geoms.push(inv.forward.predicted_footprint);
        if (inv.hindcast)
          inv.hindcast.source_region.candidate_regions.forEach((c) => geoms.push(c.geometry));
      } else {
        if (inv.hindcast) {
          geoms.push(inv.hindcast.backward_trajectory);
          inv.hindcast.source_region.candidate_regions.forEach((c) => geoms.push(c.geometry));
        }
        if (inv.vessels) inv.vessels.forEach((v) => geoms.push(v.track_geometry));
      }
      const b = geomBounds(geoms);
      if (b) map.fitBounds(boundsToLeaflet(b, 0.03), { padding: [30, 30], maxZoom: 11 });
    }
  }, [inv, selectedMmsi, onSelectVessel]);

  // ---- layer visibility -------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    const g = groupsRef.current;
    if (!map) return;
    const wanted = {
      slick: layers.slick, source: layers.source, backTraj: layers.backTraj,
      vessels: layers.vessels, release: layers.release,
      fwdTraj: layers.fwdTraj, footprint: layers.footprint,
    };
    for (const [k, on] of Object.entries(wanted)) {
      if (on && !map.hasLayer(g[k])) map.addLayer(g[k]);
      if (!on && map.hasLayer(g[k])) map.removeLayer(g[k]);
    }
  }, [layers]);

  // ---- animate drift marker along forward trajectory --------------------
  useEffect(() => {
    if (!inv.forward || !driftMarkerRef.current || !timeT) return;
    const times = inv.forward.trajectory_timestamps_utc.map((t) => new Date(t).getTime());
    const coords = lineToLatLngs(inv.forward.trajectory);
    if (!times.length || !coords.length) return;
    const t = new Date(timeT).getTime();
    let i = times.findIndex((x) => x >= t);
    if (i === -1) i = times.length - 1;
    if (i === 0) { driftMarkerRef.current.setLatLng(coords[0]); return; }
    const t0 = times[i - 1], t1 = times[i];
    const f = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
    const [la0, lo0] = coords[i - 1], [la1, lo1] = coords[i];
    driftMarkerRef.current.setLatLng([la0 + (la1 - la0) * f, lo0 + (lo1 - lo0) * f]);
  }, [timeT, inv.forward]);

  return (
    <>
      <div id="oiltrace-map" style={{ position: "absolute", inset: 0 }} />
      <div className="map-toolbar">
        {inv.slick && (
          <button className="map-btn" onClick={onOpenSar}>🛰 SAR Scene</button>
        )}
      </div>
      {inv.demo && <div className="map-badge">DEMO SCENARIO · SYNTHETIC AIS</div>}
      <div className="map-legend">
        <div className="row"><span className="layer-key" style={{ background: COL.slick, opacity: 0.7, width: 16, height: 11, borderRadius: 3 }} />Observed slick</div>
        <div className="row"><span className="layer-key" style={{ background: COL.source, opacity: 0.6, width: 16, height: 11, borderRadius: 3 }} />Source region (prob. mass)</div>
        <div className="row"><span style={{ borderTop: `2.5px dashed ${COL.backTraj}`, width: 16 }} />Backward trajectory</div>
        <div className="row"><span style={{ borderTop: `2.5px dotted ${COL.fwd}`, width: 16 }} />Forward trajectory</div>
        <div className="row"><span className="layer-key" style={{ background: COL.foot, opacity: 0.6, width: 16, height: 11, borderRadius: 3 }} />Predicted footprint</div>
        <div className="row"><span style={{ width: 16, textAlign: "center", fontSize: 10, letterSpacing: 2, color: "#10141a" }}>•••</span>Simulated drift particles</div>
        <div style={{ fontSize: 9.5, color: "var(--mut)", maxWidth: 172, lineHeight: 1.35, marginTop: 2 }}>
          Particle cloud illustrates the model trajectory &amp; uncertainty envelope.
        </div>
      </div>
      <div className="footer-line">{SAR_CREDIT}</div>
    </>
  );
}
