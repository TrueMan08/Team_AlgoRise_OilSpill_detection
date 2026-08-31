import { useState } from "react";
import { SAR_VIEWS, SAR_CREDIT } from "../demo.js";
import { fmtUtc } from "../geo.js";

export default function SarPanel({ slick, onClose }) {
  const [view, setView] = useState(SAR_VIEWS[0]);
  return (
    <div className="sar-overlay" onClick={onClose}>
      <div className="sar-card" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.14em", color: "#7fb1d8" }}>
              SATELLITE IMAGERY · DEMO SCENARIO
            </div>
            <div style={{ fontSize: 17, fontWeight: 700, marginTop: 2 }}>Sentinel-1 SAR — detection view</div>
          </div>
          <button className="map-btn" onClick={onClose}>✕ Close</button>
        </div>
        <div className="sar-hero" style={{ position: "relative" }}>
          <span className="sar-tag">{view.caption}</span>
          <img src={view.src} alt={view.caption} />
        </div>
        <div className="sar-strip">
          {SAR_VIEWS.map((v) => (
            <button key={v.id} className={view.id === v.id ? "sel" : ""} onClick={() => setView(v)}>
              <img src={v.src} alt={v.label} style={{ height: 64, width: "100%", objectFit: "cover" }} />
            </button>
          ))}
        </div>
        <div className="sar-meta">
          <div><span>Slick ID</span><b>{slick.id}</b></div>
          <div><span>Detection time</span><b>{fmtUtc(slick.timestamp_utc)}</b></div>
          <div><span>Area</span><b>{slick.area_km2.toFixed(1)} km²</b></div>
          <div><span>Confidence</span><b>{slick.confidence.toFixed(2)}</b></div>
          <div><span>Sensor</span><b>{slick.sensor || "—"}</b></div>
          <div><span>Scene</span><b>{slick.scene_id || "—"}</b></div>
        </div>
        <div style={{ marginTop: 10, fontSize: 10.5, color: "#7f97ad" }}>{SAR_CREDIT}</div>
      </div>
    </div>
  );
}
