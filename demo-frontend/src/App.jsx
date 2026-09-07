import {
  Fragment,
  useEffect,
  useMemo,
  useState,
  useCallback,
  useRef,
} from "react";

import {
  MapContainer,
  TileLayer,
  Marker,
  Tooltip,
  Polyline,
  Polygon,
  Circle,
  CircleMarker,
  useMap,
  useMapEvents,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import L from "leaflet";

import incidentData from "./data/incident.json";

import ReplayPanel from "./components/ReplayPanel";
import EvidencePanel from "./components/EvidencePanel";
import "./components/EvidencePanel.css";

import { SuspectPanel } from "./components/SuspectPanel";
import Sidebar from "./Sidebar";

import DeckOilOverlay from "./components/DeckOilOverlay";
import { DetectionPanel } from "./components/DetectionPanel";
import InvestigationList from "./components/InvestigationList";
import { TimelineControl } from "./components/TimelineControl";
import CommandTopBar from "./components/CommandTopBar";
import IntelRail from "./components/IntelRail";
import OperationCard from "./components/OperationCard";
import "./components/InvestigationList.css";

import "./App.css";
import "./stitch-theme.css";

import {
  warmBackend,
  getBackendHealth,
  runHindcast,
  getCandidateVessels,
  runAttribution,
  runForwardSimulation,
  runCounterfactual,
  getReplay,
  bboxFromGeometry,
  trajectoryPoints,
  sourceRegionForFrontend,
  slickFromDetection,
  aisPositionAt,
  slickFromIncident,
  normalizeVessels,
  buildFrontendScoring,
  shiftIsoHours,
  assertWithinForcingCoverage,
  getActiveBackendUrl,
  describeHindcastFailure,
  describeEmptyMediterraneanAis,
  CANONICAL_INCIDENT_ID,
  CANONICAL_AIS_BBOX,
  CANONICAL_AIS_START,
  CANONICAL_AIS_END,
  incidentFromDetection,
  vesselsNearCentroid,
} from "./services/backendApi";
import DriftCloudOverlay from "./components/DriftCloudOverlay";

/* =========================================================
   LEAFLET MARKER FIX
========================================================= */

delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

/* =========================================================
   INCIDENT DATA
========================================================= */

const INCIDENT_SEED = incidentData.incident;

/* =========================================================
   HELPERS
========================================================= */

function getConfidencePercent(confidence) {
  const value = Number(confidence);
  if (!Number.isFinite(value)) return 0;
  return Math.max(
    0,
    Math.min(100, value <= 1 ? Math.round(value * 100) : Math.round(value))
  );
}

function getVesselProbabilityClass(confidence) {
  const percentage = getConfidencePercent(confidence);
  if (percentage >= 70) return "probability-high";
  if (percentage >= 40) return "probability-medium";
  return "probability-low";
}

/* =========================================================
   VESSEL ICON
========================================================= */

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function vesselTypeLabel(vessel) {
  const raw = String(vessel?.type || "").trim();
  const lower = raw.toLowerCase();
  if (lower.includes("tanker") || lower.includes("oil")) return "Oil Tanker";
  if (lower.includes("cargo") || lower.includes("bulk")) return "Cargo Vessel";
  if (lower.includes("fish") || lower.includes("trawl")) return "Fishing Vessel";
  if (lower.includes("pass")) return "Passenger";
  if (raw) return raw;
  return "Vessel";
}

const SHIP_GLYPH = `
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#ffffff" d="M12 4.2c.5 0 .9.3 1.1.7L16.2 12H7.8l3.1-7.1c.2-.4.6-.7 1.1-.7z"/>
    <path fill="#ffffff" d="M4.4 13.2h15.2L17.8 19H6.2z"/>
    <path fill="#dbe7f2" d="M9 8.2h2v2.2H9zM13 8.2h2v2.2h-2z"/>
  </svg>
`;

function createVesselIcon({
  selected = false,
  replay = false,
  candidateRank = null,
  attributionConfidence = 0,
  name = "",
  typeLabel = "Vessel",
}) {
  const probabilityClass = getVesselProbabilityClass(attributionConfidence);
  const confidencePercent = getConfidencePercent(attributionConfidence);
  const showNameplate = selected;
  const safeName = escapeHtml(name || "Vessel");
  const safeType = escapeHtml(typeLabel);

  if (showNameplate) {
    return L.divIcon({
      className: "oiltrace-vessel-icon-wrapper",
      html: `
        <div class="vessel-glass-tag ${selected ? "is-selected" : ""} ${candidateRank === 1 ? "is-top" : ""} ${replay ? "is-replay" : ""}">
          <span class="vessel-glass-badge">${SHIP_GLYPH}</span>
          <span class="vessel-glass-copy">
            <b>${safeName}</b>
            <i>${safeType}</i>
          </span>
        </div>
      `,
      iconSize: [210, 48],
      iconAnchor: [24, 24],
      popupAnchor: [0, -26],
    });
  }

  if (replay) {
    // Sleek directional ship icon for replay animation
    const ringColor = candidateRank === 1
      ? "#ea580c"
      : selected
      ? "#2563eb"
      : "#64748b";

    return L.divIcon({
      className: "oiltrace-vessel-icon-wrapper",
      html: `
        <div class="vessel-replay-marker" style="
          position:relative;
          width:34px;
          height:34px;
          display:flex;
          align-items:center;
          justify-content:center;
        ">
          <div style="
            position:absolute;
            inset:-4px;
            border-radius:50%;
            border:2px solid ${ringColor};
            opacity:0.7;
          "></div>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
            xmlns="http://www.w3.org/2000/svg"
            style="filter:drop-shadow(0 1px 3px rgba(0,0,0,0.6))">
            <path d="M12 2 L20 20 L12 16 L4 20 Z"
              fill="${ringColor}" opacity="0.95" />
          </svg>
          <div style="
            position:absolute;
            top:-18px;
            left:50%;
            transform:translateX(-50%);
            background:${ringColor};
            color:#fff;
            font-size:9px;
            font-weight:700;
            padding:1px 5px;
            border-radius:4px;
            white-space:nowrap;
            box-shadow:0 1px 4px rgba(0,0,0,0.4);
          ">${confidencePercent}%</div>
        </div>
      `,
      iconSize:   [34, 34],
      iconAnchor: [17, 17],
      popupAnchor: [0, -20],
    });
  }

  return L.divIcon({
    className: "oiltrace-vessel-icon-wrapper",
    html: `
      <div
        class="
          oiltrace-vessel-marker
          vessel-glass-dot
          ${selected ? "is-selected" : ""}
          ${candidateRank === 1 ? "is-top-candidate" : ""}
          ${probabilityClass}
        "
        title="Vessel attribution probability: ${confidencePercent}%"
      >
        <div class="vessel-probability-label">${confidencePercent}%</div>
        <div class="vessel-probability-ring"></div>
        <div class="vessel-marker-body">
          <svg class="vessel-marker-symbol" width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="#ffffff" stroke="#0f172a" stroke-width="1.15" stroke-linejoin="round" d="M3.2 15.2h17.6L18.4 20H5.6z"/>
            <path fill="#ffffff" stroke="#0f172a" stroke-width="1.15" stroke-linejoin="round" d="M7 15.2V8.4h7.4L16.8 15.2"/>
            <path fill="#94a3b8" d="M8.1 8.4h2.2v2.4H8.1zM11.1 8.4h2.1v2.4h-2.1z"/>
          </svg>
        </div>
      </div>
    `,
    iconSize:   [58, 58],
    iconAnchor: [29, 29],
    popupAnchor: [0, -30],
  });
}

/* =========================================================
   GEOGRAPHIC DATA
========================================================= */

/* =========================================================
   MAP HELPERS
========================================================= */

function getIncidentPoints(inc = INCIDENT_SEED) {
  const points = [];

  if (Array.isArray(inc?.spillPolygon)) {
    inc.spillPolygon.forEach((point) => {
      if (Array.isArray(point) && point.length >= 2) {
        const latitude = Number(point[0]);
        const longitude = Number(point[1]);
        if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
          points.push([latitude, longitude]);
        }
      }
    });
  }

  if (
    inc?.centroid &&
    Number.isFinite(Number(inc.centroid.latitude)) &&
    Number.isFinite(Number(inc.centroid.longitude))
  ) {
    points.push([
      Number(inc.centroid.latitude),
      Number(inc.centroid.longitude),
    ]);
  }

  if (Array.isArray(inc?.vessels)) {
    inc.vessels.forEach((vessel) => {
      const latitude = Number(vessel?.position?.latitude);
      const longitude = Number(vessel?.position?.longitude);
      if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
        points.push([latitude, longitude]);
      }
    });
  }

  return points;
}

/* =========================================================
   FIT MAP
========================================================= */

function pipelineStepIndex(text) {
  const t = String(text || "").toLowerCase();
  if (t.includes("ais")) return 1;
  if (t.includes("rank") || t.includes("attrib")) return 2;
  if (t.includes("forward") || t.includes("counter")) return 3;
  return 0;
}

function MapFill() {
  const map = useMap();
  useEffect(() => {
    const container = map.getContainer()?.parentElement;
    if (!container) return undefined;
    const fit = () => map.invalidateSize({ pan: false });
    const observer = new ResizeObserver(fit);
    observer.observe(container);
    fit();
    return () => observer.disconnect();
  }, [map]);
  return null;
}

function FitMapToIncident() {
  const map = useMap();
  const hasInitializedRef = useRef(false);

  useEffect(() => {
    // Camera initialization is deliberately isolated from React UI state.
    // Selecting a vessel, opening a panel, changing theme, or changing a
    // layer must never call any Leaflet camera method.
    if (hasInitializedRef.current) return;
    hasInitializedRef.current = true;

    const points = getIncidentPoints();
    if (!points.length) return;

    // The grid layout may not have sized the map container yet on first
    // paint; fitting a 0-size map collapses to maxZoom at a bogus center.
    // Retry until the container has a real size.
    let cancelled = false;
    const fit = () => {
      if (cancelled) return;
      map.invalidateSize({ pan: false });
      const size = map.getSize();
      if (size.x < 200 || size.y < 200) {
        setTimeout(fit, 120);
        return;
      }
      // Set default zoom and center matching user screenshot (Dipkarpaz on left, spill centered at zoom 10)
      map.setView([35.6353, 34.78], 10, { animate: false });
    };
    fit();
    return () => { cancelled = true; };
  }, [map]);

  return null;
}

/* =========================================================
   INVESTIGATION FOCUS CONTROLLER
   Keeps the visible area on the spill/vessel action:
   - refits automatically as each backend stage completes
   - soft-bounds panning so the user can't drift far from the scene
========================================================= */

function MapFocusController({ storyPoints, scenePoints, stageKey }) {
  const map = useMap();
  const lastKeyRef = useRef("0-0-0");

  useEffect(() => {
    if (stageKey === "0-0-0" || stageKey === lastKeyRef.current) return;
    lastKeyRef.current = stageKey;
    // Vessels stage frames ships + spill; other stages frame the drift story.
    const pts = stageKey === "1-1-0" ? scenePoints : storyPoints;
    if (!pts.length) return;
    map.fitBounds(L.latLngBounds(pts), {
      paddingTopLeft: [24, 24],
      paddingBottomRight: [24, 80],
      maxZoom: 11,
      animate: true,
      duration: 0.9,
    });
  }, [map, stageKey, storyPoints, scenePoints]);

  useEffect(() => {
    const pts = scenePoints.length ? scenePoints : storyPoints;
    if (!pts.length) return;
    map.setMaxBounds(L.latLngBounds(pts).pad(2.5));
    L.Util.setOptions(map, { maxBoundsViscosity: 0.6 });
    if (map.getMinZoom() < 6) map.setMinZoom(6);
  }, [map, storyPoints, scenePoints]);

  return null;
}

function MapBackgroundClick({ onDeselect }) {
  useMapEvents({
    click(event) {
      const target = event?.originalEvent?.target;
      if (target?.closest?.(".oiltrace-vessel-icon-wrapper, .vessel-glass-tag, .leaflet-marker-icon")) {
        return;
      }
      onDeselect?.();
    },
  });
  return null;
}

/* =========================================================
   MAP TOOLBAR
========================================================= */

function MapToolbar({ onTriggerBacktrack, isBacktracking, storyPoints, scenePoints, actionLabel = "Run hindcast" }) {
  const map = useMap();

  const fitTo = (points) => {
    if (!points?.length) points = getIncidentPoints();
    if (!points.length) return;
    map.fitBounds(L.latLngBounds(points), {
      paddingTopLeft: [24, 24],
      paddingBottomRight: [24, 80],
      maxZoom: 12,
      animate: true,
      duration: 0.7,
    });
  };

  const handleResetView = () => fitTo(scenePoints);

  const handleFullscreen = () => {
    const mapElement = document.querySelector(".map");
    if (!mapElement) return;
    if (!document.fullscreenElement) {
      mapElement.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  };

  return (
    <div className="oiltrace-map-toolbar" aria-label="Map controls">
      <button
        type="button"
        className="map-tool-button backtrack-tool-button"
        onClick={onTriggerBacktrack}
        disabled={isBacktracking}
        title={actionLabel}
      >
        {isBacktracking ? "…" : "↩"}
      </button>

      <span className="map-tool-divider" />

      <button
        type="button"
        className="map-tool-button zoom-button"
        onClick={() => map.zoomIn()}
        title="Zoom in"
        aria-label="Zoom in"
      >
        +
      </button>

      <button
        type="button"
        className="map-tool-button zoom-button"
        onClick={() => map.zoomOut()}
        title="Zoom out"
        aria-label="Zoom out"
      >
        −
      </button>

      <span className="map-tool-divider" />

      <button
        type="button"
        className="map-tool-button"
        onClick={handleResetView}
        title="Reset view — spill + all vessels"
        aria-label="Reset view to spill and vessels"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="7" />
          <circle cx="12" cy="12" r="2" />
          <path d="M12 2v3" />
          <path d="M12 19v3" />
          <path d="M2 12h3" />
          <path d="M19 12h3" />
        </svg>
      </button>

      <button
        type="button"
        className="map-tool-button"
        onClick={() => fitTo(storyPoints)}
        title="Focus spill — slick, source region & drift"
        aria-label="Focus on the oil spill drift story"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 4c3.2 4 5.6 6.9 5.6 9.8a5.6 5.6 0 1 1-11.2 0C6.4 10.9 8.8 8 12 4z" />
        </svg>
      </button>

      <button
        type="button"
        className="map-tool-button"
        onClick={handleFullscreen}
        title="Fullscreen"
        aria-label="Fullscreen"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M8 3H3v5" />
          <path d="M3 3l6 6" />
          <path d="M16 3h5v5" />
          <path d="M21 3l-6 6" />
          <path d="M8 21H3v-5" />
          <path d="M3 21l6-6" />
          <path d="M16 21h5v-5" />
          <path d="M21 21l-6-6" />
        </svg>
      </button>

    </div>
  );
}

/* =========================================================
   VESSEL TOOLTIP
========================================================= */

function VesselPopup({ vessel, show = true }) {
  const confidencePercent = getConfidencePercent(vessel.attributionConfidence);

  if (!show) return null;

  return (
    <Tooltip
      direction="top"
      offset={[0, -22]}
      opacity={1}
      className="oiltrace-vessel-tooltip"
    >
      <div className="vessel-tooltip-content">
        <div className="vessel-tooltip-header">
          <strong>{vessel.name}</strong>
          <span
            className={`vessel-tooltip-probability ${getVesselProbabilityClass(
              vessel.attributionConfidence
            )}`}
          >
            {confidencePercent}%
          </span>
        </div>

        <div className="vessel-tooltip-row">
          <span>Type</span>
          <strong>{vessel.type}</strong>
        </div>

        <div className="vessel-tooltip-row">
          <span>Speed</span>
          <strong>{vessel.speedKnots} knots</strong>
        </div>

        <div className="vessel-tooltip-row">
          <span>Heading</span>
          <strong>{vessel.heading}°</strong>
        </div>

        <div className="vessel-tooltip-row">
          <span>Candidate rank</span>
          <strong>#{vessel.candidateRank}</strong>
        </div>

        <div className="vessel-tooltip-row">
          <span>Attribution confidence</span>
          <strong>{confidencePercent}%</strong>
        </div>
      </div>
    </Tooltip>
  );
}

/* =========================================================
   INCIDENT PANEL
========================================================= */

function IncidentPanel({ incident, vessels, onSelectVessel, onClose, onTriggerBacktrack, isBacktracking, actionLabel = "Run hindcast" }) {
  const topCandidate =
    vessels.find((vessel) => vessel.candidateRank === 1) || vessels[0];

  const detectedDate = new Date(incident.detectedAt);

  const detectedDateText = detectedDate.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

  const detectedTimeText = detectedDate.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });

  const lat = Number(incident?.centroid?.latitude ?? incident?.location?.latitude ?? 0);
  const lng = Number(incident?.centroid?.longitude ?? incident?.location?.longitude ?? 0);
  const latStr = `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? "N" : "S"}`;
  const lngStr = `${Math.abs(lng).toFixed(4)}° ${lng >= 0 ? "E" : "W"}`;
  const formattedCoordinates = `${latStr} · ${lngStr}`;

  const handleExportReport = () => {
    const timestamp = new Date().toISOString().replace(/T/, " ").substring(0, 19) + " UTC";
    const reportId = incident.id || "OT-INCIDENT-REPORT";

    let report = `================================================================================\n`;
    report += `OILTRACE — MARITIME INVESTIGATION REPORT\n`;
    report += `Generated:      ${timestamp}\n`;
    report += `Classification: OFFICIAL MARITIME REPORT (SIMULATED DATA DEMO)\n`;
    report += `================================================================================\n\n`;

    report += `1. INCIDENT IDENTIFICATION & LOCATION\n`;
    report += `--------------------------------------------------------------------------------\n`;
    report += `Incident ID:            ${incident.id || "—"}\n`;
    report += `Status:                 ${incident.status || "Under Investigation"}\n`;
    report += `Severity:               ${incident.severity || "High"}\n`;
    report += `Spill Type:             ${incident.spillType || "Suspected oil slick"}\n`;
    report += `Detected Date/Time:     ${detectedDateText} ${detectedTimeText} UTC\n`;
    report += `Centroid Coordinates:   ${latStr}, ${lngStr} (${lat.toFixed(4)}, ${lng.toFixed(4)})\n`;
    report += `Estimated Area:         ${incident.areaKm2} km²\n`;
    report += `Detection Confidence:   ${Math.round((incident.detectionConfidence || 0) * 100)}%\n`;
    report += `Satellite Platform:     ${incident.satellite?.platform || "Sentinel-1"} (${incident.satellite?.sensor || "SAR"})\n`;
    report += `Product Image ID:       ${incident.satellite?.imageId || "DEMO-S1-001"}\n\n`;

    report += `2. SOURCE ESTIMATION (HYDRODYNAMIC BACKTRACKING)\n`;
    report += `--------------------------------------------------------------------------------\n`;
    const sourceLat = incident.sourceRegion?.center?.latitude ?? lat;
    const sourceLng = incident.sourceRegion?.center?.longitude ?? lng;
    const sourceRadiusKm = ((incident.sourceRegion?.radiusMeters || 1800) / 1000).toFixed(2);
    report += `Probable Source Center: ${Math.abs(sourceLat).toFixed(4)}° ${sourceLat >= 0 ? "N" : "S"}, ${Math.abs(sourceLng).toFixed(4)}° ${sourceLng >= 0 ? "E" : "W"}\n`;
    report += `Uncertainty Radius:     ${sourceRadiusKm} km (${incident.sourceRegion?.radiusMeters || 1800} m)\n`;
    report += `Source Type:            ${incident.sourceRegion?.type || "Uncertainty region"}\n\n`;

    report += `3. CANDIDATE VESSEL ATTRIBUTION RANKING\n`;
    report += `--------------------------------------------------------------------------------\n`;
    vessels.forEach((v, idx) => {
      const conf = Math.round((v.attributionConfidence || 0) * 100);
      report += `Rank ${v.candidateRank || idx + 1}: ${v.name} [ID: ${v.id}]\n`;
      report += `  Type:                 ${v.type} | Flag: ${v.flag || "—"}\n`;
      report += `  Position:             ${Number(v.position?.latitude || 0).toFixed(4)}° N, ${Number(v.position?.longitude || 0).toFixed(4)}° E\n`;
      report += `  Speed / Heading:      ${v.speedKnots || 0} kts | ${v.heading || 0}°\n`;
      report += `  Attribution Score:    ${conf}% (${conf >= 70 ? "HIGH PROBABILITY" : conf >= 40 ? "MEDIUM PROBABILITY" : "LOW PROBABILITY"})\n`;
      if (v.evidence) {
        report += `  Evidence Breakdown:\n`;
        if (v.evidence.spatial) report += `    • Spatial Proximity:   ${Math.round((v.evidence.spatial.score || 0) * 100)}% (${v.evidence.spatial.label})\n`;
        if (v.evidence.temporal) report += `    • Temporal Overlap:    ${Math.round((v.evidence.temporal.score || 0) * 100)}% (${v.evidence.temporal.label})\n`;
        if (v.evidence.trajectory) report += `    • Trajectory Match:    ${Math.round((v.evidence.trajectory.score || 0) * 100)}% (${v.evidence.trajectory.label})\n`;
        if (v.evidence.drift) report += `    • Drift Counterfactual:${Math.round((v.evidence.drift.score || 0) * 100)}% (${v.evidence.drift.label})\n`;
        if (v.evidence.aisReliability) report += `    • AIS Coverage Status: ${v.evidence.aisReliability.status} (${v.evidence.aisReliability.label})\n`;
      }
      report += `\n`;
    });

    report += `4. INCIDENT TIMELINE\n`;
    report += `--------------------------------------------------------------------------------\n`;
    (incident.timeline || []).forEach((event) => {
      report += `${event.time} UTC  -  ${event.label}\n`;
    });
    report += `\n`;

    report += `5. DRIFT & WEATHER MODEL PARAMETERS (SIMULATED)\n`;
    report += `--------------------------------------------------------------------------------\n`;
    report += `Ocean Current:          Simulated Northwest Coastal Drift (Deterministic Field, ~1.8 m/s)\n`;
    report += `Atmospheric Wind:       Simulated NNW 5.2 m/s (Standard 3.0% windage coefficient)\n`;
    report += `Lagrangian Dispersion:  OpenDrift / OpenOil modeled particle advection & backward tracking\n\n`;

    report += `================================================================================\n`;
    report += `DISCLAIMER: All vessel positions, sensor data, and attribution scores in this\n`;
    report += `report are simulated for evaluation of the OilTrace automated attribution engine.\n`;
    report += `================================================================================\n`;

    const blob = new Blob([report], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `OILTRACE-REPORT-${reportId}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <aside
      className="oiltrace-context-panel incident-context-panel"
      aria-label="Incident information"
    >
      <div className="context-panel-header">
        <div>
          <span className="context-kicker">INCIDENT</span>
          <h2>{incident.id}</h2>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <button
            type="button"
            className="incident-export-button"
            onClick={handleExportReport}
            title="Export full incident investigation report"
          >
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span>Report</span>
          </button>

          <button
            type="button"
            className="context-close-button"
            onClick={onClose}
            aria-label="Close incident panel"
          >
            ×
          </button>
        </div>
      </div>



      <section className="context-section">
        <span className="context-section-label">INCIDENT</span>
        <h3 className="incident-title">{incident.spillType}</h3>
        <div className="incident-coord-chip">
          <span>{formattedCoordinates}</span>
        </div>
        <p className="incident-time" style={{ marginTop: "6px" }}>
          {detectedDateText} · {detectedTimeText} UTC
        </p>
      </section>

      <section className="context-section">
        <span className="context-section-label">SPILL ASSESSMENT</span>
        <div className="incident-metrics">
          <div className="incident-metric">
            <strong>{incident.areaKm2}</strong>
            <span>km²</span>
            <small>AREA</small>
          </div>

          <div className="incident-metric">
            <strong>
              {Math.round(incident.detectionConfidence * 100)}%
            </strong>
            <span>confidence</span>
            <small>DETECTION</small>
          </div>

          <div className="incident-metric">
            <strong>{incident.satellite.platform}</strong>
            <span>{incident.satellite.sensor}</span>
            <small>SENSOR</small>
          </div>
        </div>
      </section>

      <section className="context-section">
        <span className="context-section-label">SOURCE ESTIMATION</span>
        <h4 className="incident-title">Backward trajectory</h4>
        <p className="incident-time">
          Reconstruct oil transport back from detection to estimate the origin region.
        </p>
        <button
          type="button"
          className="inspect-candidate-button"
          onClick={onTriggerBacktrack}
          disabled={isBacktracking}
        >
          {isBacktracking ? "Running…" : actionLabel}
        </button>
      </section>

      <section className="context-section">
        <div className="context-section-heading">
          <span className="context-section-label">INVESTIGATION</span>
          <span className="candidate-count">{vessels.length}</span>
        </div>

        <div className="incident-candidate-summary">
          <div>
            <span className="candidate-summary-label">TOP CANDIDATE</span>
            <strong>{topCandidate?.name || "No candidate"}</strong>
          </div>

          {topCandidate && (
            <div className="candidate-confidence">
              <strong>
                {getConfidencePercent(topCandidate.attributionConfidence)}%
              </strong>
              <span>attribution</span>
            </div>
          )}
        </div>

        {topCandidate && (
          <button
            type="button"
            className="inspect-candidate-button"
            onClick={() => onSelectVessel(topCandidate)}
          >
            Inspect candidate <span>→</span>
          </button>
        )}
      </section>

      <section className="context-section">
        <span className="context-section-label">TIMELINE</span>
        <div className="incident-timeline">
          {(incident.timeline || []).map((event, index) => (
            <div
              className={`incident-timeline-item ${
                index === (incident.timeline || []).length - 1 ? "timeline-final" : ""
              }`}
              key={`${event.time}-${index}`}
            >
              <div className="timeline-marker">
                <span />
              </div>
              <div className="timeline-content">
                <strong>{event.time}</strong>
                <span>{event.label}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}

/* =========================================================
   LEGEND
========================================================= */

function LegendPanel({ onClose }) {
  return (
    <aside className="oiltrace-context-panel legend-context-panel" aria-label="Map legend">
      <div className="context-panel-header legend-panel-header">
        <div>
          <span className="context-kicker">MAP REFERENCE</span>
          <h2>Legend</h2>
          <p className="legend-panel-subtitle">Map symbols and investigation layers</p>
        </div>

        <button type="button" className="context-close-button" onClick={onClose} aria-label="Close legend">
          ×
        </button>
      </div>

      <div className="legend-content">
        <section className="legend-group">
          <div className="legend-group-title">WHAT THE MAP IS SHOWING</div>
          <div className="legend-items legend-items-lg">
            <div className="legend-item"><span className="legend-swatch" style={{ background: "rgba(239,68,68,0.32)", border: "2px solid #ef4444" }} /><span><strong>Observed slick</strong> — detected by SAR</span></div>
            <div className="legend-item"><span className="legend-swatch" style={{ background: "rgba(59,130,246,0.10)", border: "2px dashed #3b82f6" }} /><span><strong>Probable source region</strong> — where the oil came from (hindcast)</span></div>
            <div className="legend-item"><span className="legend-dot" style={{ background: "#ffffff", border: "3px solid #dc2626" }} /><span><strong>Estimated release</strong> — suspected leak point &amp; time</span></div>
            <div className="legend-item"><span className="legend-swatch" style={{ background: "rgba(16,185,129,0.2)", border: "2px solid #059669" }} /><span><strong>Predicted footprint</strong> — where the simulated oil ends up</span></div>
            <div className="legend-item"><span className="legend-dot" style={{ background: "#0db2c8" }} /><span><strong>Backward drift</strong> — slick traced back to source (before release)</span></div>
            <div className="legend-item"><span className="legend-dot" style={{ background: "#22c55e" }} /><span><strong>Forward drift</strong> — oil released and drifting to the slick (after release)</span></div>
            <div className="legend-item"><span className="legend-dot" style={{ background: "#64748b" }} /><span>Observed slick particle field</span></div>
            <div className="legend-item"><span className="legend-line" style={{ backgroundColor: "#0284c7" }} /><span>Ocean current field</span></div>
            <div className="legend-item"><span className="legend-line" style={{ backgroundColor: "#f59e0b" }} /><span>Wind field</span></div>
          </div>
        </section>

        <section className="legend-group">
          <div className="legend-group-title">VESSELS / TRAJECTORIES</div>
          <div className="legend-items">
            <div className="legend-item"><span className="legend-vessel"><span>⚓</span></span><span>Candidate vessel</span></div>
            <div className="legend-item"><span className="legend-vessel legend-top-vessel"><span>⚓</span></span><span>Top candidate</span></div>
            <div className="legend-item"><span className="legend-line legend-selected" /><span>Selected vessel trajectory</span></div>
            <div className="legend-item"><span className="legend-line legend-candidate" /><span>Top candidate trajectory</span></div>
            <div className="legend-item"><span className="legend-line legend-muted-trajectory" /><span>Other vessel trajectory</span></div>
          </div>
        </section>

        <section className="legend-group">
          <div className="legend-group-title">ATTRIBUTION CONFIDENCE</div>
          <div className="legend-items">
            <div className="legend-item"><span className="legend-probability-dot probability-high-dot" /><span>High attribution · 70–100%</span></div>
            <div className="legend-item"><span className="legend-probability-dot probability-medium-dot" /><span>Medium attribution · 40–69%</span></div>
            <div className="legend-item"><span className="legend-probability-dot probability-low-dot" /><span>Low attribution · 0–39%</span></div>
          </div>
        </section>

        <div className="legend-note">
          <strong>EVIDENCE, NOT ACCUSATION</strong>
          <p>Drift clouds are OpenDrift/OpenOil Lagrangian particles advected by the backend&apos;s ocean-current and wind forcing. The teal cloud plays before the estimated release, tracing the slick backwards; the green cloud plays after it, carrying the simulated leak forward to the observed slick.</p>
          <p>Scores are spatial, temporal and physical-consistency evidence — never proof of vessel responsibility.</p>
        </div>
      </div>
    </aside>
  );
}

/* =========================================================
   APP
========================================================= */

function App() {
  const [incident, setIncident] = useState(INCIDENT_SEED);
  const spillPolygon = useMemo(() => {
    // The observed slick layer renders ONLY the real detection footprint
    // (incident.spillPolygon is [lat, lon] pairs derived from the detection
    // geometry). No geometry → nothing is drawn; a synthetic stand-in
    // polygon would be an invented observation.
    return (incident?.spillPolygon || []).filter(
      (pt) => Array.isArray(pt) && Number.isFinite(+pt[0]) && Number.isFinite(+pt[1])
    );
  }, [incident]);

  /* =======================================================
     DYNAMIC BACKTRACK ENGINE STATE
  ======================================================= */

  const [backtrackResult, setBacktrackResult] = useState(null);
  const [attributionResult, setAttributionResult] = useState(null);
  const [isBacktracking, setIsBacktracking] = useState(false);
  const [backtrackStatusText, setBacktrackStatusText] = useState("");

  // Live backend investigation artifacts (null until the pipeline runs)
  const [backendVessels, setBackendVessels] = useState(null);
  // Per-candidate counterfactual state, keyed by MMSI. Candidate A's result
  // is never overwritten when candidate B finishes.
  const [forwardResults, setForwardResults] = useState({});
  const [counterfactualResults, setCounterfactualResults] = useState({});
  const [counterfactualNotes, setCounterfactualNotes] = useState({});
  const [commonTestResults, setCommonTestResults] = useState({});
  const [commonReleaseIso, setCommonReleaseIso] = useState(null);
  const [cfProgress, setCfProgress] = useState(null);
  const [selectedVesselId, setSelectedVesselId] = useState(null);

  // The selected candidate's OWN results. Selecting another vessel switches
  // the plume, release marker, footprint and evidence to that vessel's
  // cached backend result — nothing is recomputed and nothing is stale.
  const selectedForward = useMemo(() => {
    const key = String(selectedVesselId ?? "");
    if (key && forwardResults[key]) return forwardResults[key];
    const first = Object.keys(forwardResults)[0];
    return first ? forwardResults[first] : null;
  }, [forwardResults, selectedVesselId]);

  const selectedCounterfactual = useMemo(() => {
    const key = String(selectedVesselId ?? "");
    if (key && counterfactualResults[key]) return counterfactualResults[key];
    const first = Object.keys(counterfactualResults)[0];
    return first && !key ? counterfactualResults[first] : null;
  }, [counterfactualResults, selectedVesselId]);

  const anyForward = useMemo(
    () => Object.keys(forwardResults).length > 0,
    [forwardResults]
  );
  const [backendError, setBackendError] = useState(null);
  const [backendOnline, setBackendOnline] = useState(null); // null=checking
  const [backendHost, setBackendHost] = useState("");
  const [transposeNotice, setTransposeNotice] = useState(null);
  const [replayMeta, setReplayMeta] = useState(null);
  const [activeSlick, setActiveSlick] = useState(null); // slick sent to the backend

  // Observed slick centroid: the detection's own centroid, never a
  // hardcoded coordinate and never shared with source/release markers.
  const observedCentroid = useMemo(() => {
    const c = activeSlick?.centroid;
    const lat = Number(c?.lat ?? incident?.centroid?.latitude);
    const lon = Number(c?.lon ?? incident?.centroid?.longitude);
    return Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : null;
  }, [activeSlick, incident]);


  const calculatedSourceRegion = backtrackResult?.sourceRegion || null;

  const candidateRegionsList = useMemo(() => {
    const raw =
      backtrackResult?.backend?.source_region?.candidate_regions ||
      backtrackResult?.source_region?.candidate_regions ||
      calculatedSourceRegion?.candidate_regions ||
      [];
    return raw.map((r, i) => {
      const coords = r.geometry?.coordinates?.[0] || [];
      const ring = coords
        .map(([lon, lat]) => [Number(lat), Number(lon)])
        .filter(([lat, lon]) => Number.isFinite(lat) && Number.isFinite(lon));
      const cent = r.centroid
        ? [Number(r.centroid.lat ?? r.centroid.latitude), Number(r.centroid.lon ?? r.centroid.longitude)]
        : null;
      return {
        id: r.id || `candidate-${i + 1}`,
        ring,
        centroid: cent,
        probability: Number(r.probability ?? 0.95),
        startTime: r.start_time_utc,
        endTime: r.end_time_utc,
      };
    }).filter((r) => r.ring.length >= 3);
  }, [backtrackResult, calculatedSourceRegion]);

  // Forward simulation's predicted particle envelope (stage 3).
  const predictedFootprintRing = useMemo(() => {
    const geom = selectedForward?.predicted_footprint;
    const coords = geom?.coordinates?.[0] || [];
    return coords
      .map(([lon, lat]) => [Number(lat), Number(lon)])
      .filter(([lat, lon]) => Number.isFinite(lat) && Number.isFinite(lon));
  }, [selectedForward]);

  // Estimated release point: from the forward run once it exists, otherwise
  // from the attribution's leading candidate.
  const releasePoint = useMemo(() => {
    const src = selectedForward?.release_location
      ? { loc: selectedForward.release_location, t: selectedForward.release_time_utc }
      : attributionResult?.top_candidates?.[0]?.release_location
        ? {
            loc: attributionResult.top_candidates[0].release_location,
            t: attributionResult.top_candidates[0].release_time_utc,
          }
        : null;
    if (!src) return null;
    const lat = Number(src.loc.lat ?? src.loc.latitude);
    const lon = Number(src.loc.lon ?? src.loc.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    return { position: [lat, lon], time: src.t };
  }, [selectedForward, attributionResult]);

  const scoredVessels = useMemo(
    // Vessels appear only once the hindcast pipeline has queried AIS —
    // never from the bundled demo incident.
    () => vesselsNearCentroid(backendVessels || [], incident.centroid),
    [backendVessels, incident]
  );


  // Seed vessel for the local oil simulation: prefer backend-flagged culprit,
  // then the attribution winner, then the tanker from the demo scene. The
  // static fallback only positions the simulation — it carries no score.
  const topVessel = scoredVessels[0] || null;

  /* =======================================================
     LIVE FOCUS GEOMETRY (what the camera should frame)
  ======================================================= */

  // "Story": where the oil is — slick, source region, drift trajectories,
  // predicted footprint. Always from the live investigation state.
  const storyPoints = useMemo(() => {
    const pts = [];
    const pushRing = (ring) =>
      (ring || []).forEach(([lon, lat]) => pts.push([+lat, +lon]));
    const pushGeom = (g) => {
      if (!g) return;
      if (g.type === "Polygon") g.coordinates.forEach(pushRing);
      else if (g.type === "MultiPolygon")
        g.coordinates.forEach((poly) => poly.forEach(pushRing));
      else if (g.type === "LineString") pushRing(g.coordinates);
    };
    if (activeSlick?.geometry) pushGeom(activeSlick.geometry);
    else spillPolygon.forEach((p) => pts.push(p));
    pushGeom(calculatedSourceRegion?.geometry);
    if (calculatedSourceRegion?.center)
      pts.push([
        +calculatedSourceRegion.center.latitude,
        +calculatedSourceRegion.center.longitude,
      ]);
    (backtrackResult?.trajectory || []).forEach((p) =>
      pts.push([+p.latitude, +p.longitude])
    );
    pushGeom(selectedForward?.trajectory);
    pushGeom(selectedForward?.predicted_footprint);
    return pts.filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b));
  }, [activeSlick, calculatedSourceRegion, backtrackResult, selectedForward, spillPolygon]);

  // "Scene": story + every vessel's track — spill AND ships in frame.
  const scenePoints = useMemo(() => {
    const pts = [...storyPoints];
    scoredVessels.forEach((v) => {
      if (v.position)
        pts.push([+v.position.latitude, +v.position.longitude]);
      (v.trajectory || []).forEach((p) =>
        pts.push([+p.latitude, +p.longitude])
      );
    });
    return pts.filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b));
  }, [storyPoints, scoredVessels]);

  const focusStageKey = `${backtrackResult ? 1 : 0}-${backendVessels ? 1 : 0}-${anyForward ? 1 : 0}`;

  /* =======================================================
     MASTER SIMULATION CLOCK
     One UTC clock spanning the backend simulation window
     drives the Replay panel, the vessel replay AND the
     drift particle cloud - everything stays in sync.
  ======================================================= */

  // ONE shared UTC investigation clock. Its window comes from the backend
  // replay (start/end or the frame timestamps themselves) whenever that is
  // available; the detection-time fallback only covers the moments before
  // the replay metadata has loaded.
  const simRange = useMemo(() => {
    const replayStart = Date.parse(replayMeta?.start_time_utc);
    const replayEnd = Date.parse(replayMeta?.end_time_utc);
    if (Number.isFinite(replayStart) && Number.isFinite(replayEnd) && replayEnd > replayStart) {
      return { t0: replayStart, t1: replayEnd };
    }
    const frameTs = (replayMeta?.frames || [])
      .map((f) => Date.parse(f?.timestamp_utc))
      .filter(Number.isFinite);
    if (frameTs.length >= 2) {
      return { t0: Math.min(...frameTs), t1: Math.max(...frameTs) };
    }
    const detected = Date.parse(incident?.detectedAt) || Date.UTC(2024, 7, 26, 12);
    return { t0: detected - 6 * 60 * 60 * 1000, t1: detected };
  }, [replayMeta, incident]);

  const [simMs, setSimMs] = useState(Date.UTC(2024, 7, 26, 6));

  const fmtSimClock = (ms) => {
    if (!Number.isFinite(ms)) return null;
    const d = new Date(ms);
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  };

  /* =======================================================
     ACTIVE SIDEBAR ITEM & THEME
  ======================================================= */

  const [activeItem, setActiveItem] = useState("map");
  const [mapStyle, setMapStyle] = useState("map");

  /* =======================================================
     SELECTED VESSEL
  ======================================================= */

  const [queueQuery, setQueueQuery] = useState("");

  const selectedVessel = scoredVessels.find(
    (vessel) => vessel.id === selectedVesselId
  );

  // The counterfactual describes exactly one vessel. Showing it under any
  // other candidate would attribute one ship's drift evidence to another.

  /* =======================================================
     MAP LAYERS
  ======================================================= */

  const [layers, setLayers] = useState({
    spill: true,
    oilTrajectory: true,
    backtrack: true,
    sourceRegion: true,
    trajectories: true,
    vessels: true,
    oceanCurrent: true,
    windField: true,
    detectedSlicks: true,
  });

  /* =======================================================
     DETECTION API STATE
  ======================================================= */

  // GeoJSON FeatureCollection returned by the Detection Service, or null
  const [detectionResult, setDetectionResult] = useState(null);

  // Backtrack seed override: { lat, lon } from a detected slick centroid
  const [apiSeedOverride, setApiSeedOverride] = useState(null);
  // Which slick ID is the active seed (for button highlight)
  const [activeSeedId, setActiveSeedId] = useState(null);

  // Fire-and-forget warm-up on mount so the backend is ready.
  // Detection is deliberately NOT auto-loaded: the scene stays empty until
  // the operator loads a SAR detection, which reveals the slick and unlocks
  // the hindcast stage. (The previous auto-load here also called two
  // functions that were never imported — a ReferenceError waiting on the
  // VITE_USE_MODAL_ML flag.)
  useEffect(() => {
    warmBackend();

    // Poll health rather than probing once on mount: a single check meant
    // that a backend which was down at page load (or restarted afterwards)
    // left the badge stuck reading "Local offline" forever, and a backend
    // that died mid-session still showed as online.
    let cancelled = false;
    const checkHealth = () => {
      getBackendHealth()
        .then(() => {
          if (cancelled) return;
          setBackendOnline(true);
          setBackendHost(getActiveBackendUrl());
        })
        .catch(() => {
          if (cancelled) return;
          setBackendOnline(false);
          setBackendHost(getActiveBackendUrl());
        });
    };
    checkHealth();
    const healthTimer = setInterval(checkHealth, 15000);

    // Prefetch replay metadata for the Replay panel, but do NOT surface any
    // vessels yet: candidates appear only after "Run hindcast" queries AIS
    // and the attribution pipeline scores them.
    getReplay(CANONICAL_INCIDENT_ID)
      .then((replay) => {
        if (!cancelled) setReplayMeta(replay);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      clearInterval(healthTimer);
    };
  }, []);

  // `gen` is captured by the panel BEFORE its request starts, so a detection
  // that lands after a Reset is discarded instead of resurrecting the stage.
  const handleDetectionResult = useCallback((geojson, gen) => {
    if (gen != null && gen !== runGenerationRef.current) return;
    setDetectionResult(geojson);
    // Auto-enable the detected slicks layer when results arrive
    setLayers((prev) => ({ ...prev, detectedSlicks: true }));

    // The detection response is the canonical incident state: geometry,
    // centroid, area, confidence and observation time all flow from here
    // into every panel and map layer — no component keeps its own copy.
    const feature = geojson?.features?.[0];
    if (!feature) return;
    setIncident(incidentFromDetection(feature, INCIDENT_SEED));
    const slick = slickFromDetection(feature);
    setActiveSlick({
      ...slick,
      id: CANONICAL_INCIDENT_ID,
      timestamp_utc: slick.timestamp_utc || INCIDENT_SEED.detectedAt,
    });
    setActiveSeedId(feature.properties?.id || CANONICAL_INCIDENT_ID);
  }, []);

  const handleSeedOverride = useCallback(({ lat, lon }, slickId) => {
    setApiSeedOverride({ lat, lon });
    setActiveSeedId(slickId);
  }, []);

  const handleClearSeed = useCallback(() => {
    setApiSeedOverride(null);
    setActiveSeedId(null);
  }, []);

  const toggleLayer = (layer) => {
    setLayers((previous) => ({
      ...previous,
      [layer]: !previous[layer],
    }));
  };

  /* =======================================================
     REPLAY CONTROLS
  ======================================================= */

  const [isPlaying, setIsPlaying] = useState(false);

  // The detection reveal + replay gates: the slick/probable region appears
  // only after a detection is loaded (or the pipeline ran), and playback is
  // meaningful only once the hindcast has produced trajectories.
  const hasDetection = Boolean(detectionResult || activeSeedId || backtrackResult);
  const canReplay = Boolean(backtrackResult);
  const guardedSetIsPlaying = useCallback(
    (value) => {
      setIsPlaying((prev) => {
        const next = typeof value === "function" ? value(prev) : value;
        return canReplay ? next : false;
      });
    },
    [canReplay]
  );
  const [replayProgress, setReplayProgress] = useState(0);
  const [replaySpeed, setReplaySpeed] = useState(1);

  const totalReplayPoints = useMemo(() => {
    const fromReplay = replayMeta?.frames?.length || 0;
    const fromTracks = scoredVessels.length
      ? Math.max(...scoredVessels.map((vessel) => vessel.trajectory?.length || 1))
      : 0;
    return Math.max(1, fromReplay, fromTracks);
  }, [scoredVessels, replayMeta]);


  /* =======================================================
     REPLAY ENGINE
  ======================================================= */

  // ONE master clock, direction-aware. A playback plan says where the clock
  // travels FROM and TO in real UTC milliseconds; hindcast plans run
  // BACKWARD (12:00 → 06:00), forward plans run forward (release → obs).
  // Timestamps are never reinterpreted — the clock itself changes direction.
  //
  // BASE_PLAYBACK_MS is the full-plan duration at 1×, so the speed chips map
  // to: 0.5× ≈ 120 s · 1× ≈ 60 s · 2× ≈ 30 s · 4× ≈ 15 s.
  const BASE_PLAYBACK_MS = 60000;
  const playPlanRef = useRef(null);
  // Incremented by Reset; async work captures the value it started under and
  // discards its results if the investigation has since been reset.
  const runGenerationRef = useRef(0);

  const startPlayback = useCallback((fromMs, toMs) => {
    if (!Number.isFinite(fromMs) || !Number.isFinite(toMs) || fromMs === toMs) return;
    playPlanRef.current = { from: fromMs, to: toMs };
    setSimMs(fromMs);
    setIsPlaying(true);
  }, []);

  useEffect(() => {
    if (!isPlaying) return undefined;

    const fallback = simRange
      ? { from: Number.isFinite(simMs) ? simMs : simRange.t0, to: simRange.t1 }
      : null;
    const plan =
      playPlanRef.current &&
      Number.isFinite(playPlanRef.current.from) &&
      Number.isFinite(playPlanRef.current.to)
        ? playPlanRef.current
        : fallback;
    if (!plan || plan.from === plan.to) return undefined;

    const dir = plan.to >= plan.from ? 1 : -1;
    let cur = Number.isFinite(simMs) ? simMs : plan.from;
    // Restart from the top of the plan when the clock already sits at (or
    // beyond) its end, or outside the plan window entirely.
    const before = dir === 1 ? cur < plan.from : cur > plan.from;
    const done0 = dir === 1 ? cur >= plan.to - 500 : cur <= plan.to + 500;
    if (before || done0) cur = plan.from;

    const span = Math.abs(plan.to - plan.from);
    const rate = (span / BASE_PLAYBACK_MS) * replaySpeed * dir; // sim-ms per real-ms
    let raf, last = performance.now();
    const tick = (now) => {
      cur += (now - last) * rate;
      last = now;
      const finished = dir === 1 ? cur >= plan.to : cur <= plan.to;
      if (finished) {
        setSimMs(plan.to);
        setIsPlaying(false);
        return;
      }
      setSimMs(cur);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlaying, replaySpeed, simRange]);

  /* =======================================================
     BACKTRACK RUNNER
  ======================================================= */

  // The live investigation now runs as three OPERATOR-TRIGGERED stages:
  //   1. Run hindcast     — slick drifts backwards on the forcing fields and
  //                         a probable source region forms with confidence.
  //   2. Run attribution  — AIS traffic inside that region is scanned and
  //                         ranked; the most probable ships are presented.
  //   3. Forward simulation — the top suspect's release is simulated forward
  //                         (counterfactual) and scored against the slick.

  // STAGE 1 — hindcast
  const handleRunHindcastStage = useCallback(async () => {
    const gen = runGenerationRef.current;
    setActiveItem("map");

    let slick = null;
    if (activeSeedId && detectionResult?.features?.length) {
      const feature = detectionResult.features.find(
        (f) => String(f?.properties?.id) === String(activeSeedId)
      );
      if (feature) slick = slickFromDetection(feature);
    }
    if (slick && apiSeedOverride) {
      slick = {
        ...slick,
        centroid: { lat: apiSeedOverride.lat, lon: apiSeedOverride.lon },
      };
    }
    if (!slick) slick = slickFromIncident(incident);
    slick = {
      ...slick,
      id: CANONICAL_INCIDENT_ID,
      timestamp_utc: slick.timestamp_utc || incident.detectedAt,
    };

    assertWithinForcingCoverage(slick);
    setTransposeNotice(null);
    setActiveSlick(slick);
    setForwardResults({});
    setCounterfactualResults({});
    setCommonTestResults({});
    setCommonReleaseIso(null);
    setCounterfactualNotes({});
    setCfProgress(null);
    setAttributionResult(null);

    // The backend OpenDrift hindcast is the ONLY source of the backward
    // reconstruction. No local physics preview (drift physics do not belong
    // in the frontend) and no synthetic fallback: if the call fails, the
    // error propagates to the dispatcher and is shown to the operator.
    setBacktrackStatusText("OpenDrift hindcast…");
    const hc = await runHindcast(slick, 6);
    if (runGenerationRef.current !== gen) return; // reset while in flight

    const sourceRegion = sourceRegionForFrontend(hc.source_region);
    setBacktrackResult({
      sourceRegion,
      sourceEstimate: {
        latitude: sourceRegion.center.latitude,
        longitude: sourceRegion.center.longitude,
      },
      confidence: sourceRegion.confidence,
      uncertainty: {
        radiusMeters: sourceRegion.radiusMeters,
        radiusKm: Number((sourceRegion.radiusMeters / 1000).toFixed(2)),
        confidence: sourceRegion.confidence,
        particleConvergence: "Backend OpenDrift hindcast",
      },
      trajectory: trajectoryPoints(hc.backward_trajectory),
      backend: hc,
    });
    setIncident((prev) => ({ ...prev, sourceRegion }));
    setBackendOnline(true);
    setBackendHost(getActiveBackendUrl());

    // HINDCAST playback runs BACKWARD: from the observation time down to
    // the earliest backend hindcast timestamp — the clock itself decreases.
    const simTs = (hc.trajectory_timestamps_utc || [])
      .map((t) => Date.parse(t))
      .filter(Number.isFinite);
    const obsT = Date.parse(slick.timestamp_utc);
    const traceEnd = simTs.length ? Math.min(...simTs) : NaN;
    if (Number.isFinite(obsT) && Number.isFinite(traceEnd) && traceEnd < obsT) {
      startPlayback(obsT, traceEnd);
    }

    try {
      const replay = await getReplay(CANONICAL_INCIDENT_ID);
      if (runGenerationRef.current === gen) setReplayMeta(replay);
    } catch {
      /* replay is optional */
    }
  }, [activeSeedId, detectionResult, apiSeedOverride, incident, startPlayback]);

  // STAGE 2 — AIS scan + attribution over the probable source region
  const handleRunAttributionStage = useCallback(async () => {
    const gen = runGenerationRef.current;
    const hc = backtrackResult?.backend;
    const slick = activeSlick;
    if (!hc || !slick) return;

    const region = hc.source_region?.candidate_regions?.[0];
    const bbox = region?.geometry
      ? bboxFromGeometry(region.geometry, 0.6)
      : CANONICAL_AIS_BBOX;
    const start = region?.start_time_utc
      ? shiftIsoHours(region.start_time_utc, -12)
      : CANONICAL_AIS_START;
    const end = region?.end_time_utc
      ? shiftIsoHours(region.end_time_utc, 12)
      : CANONICAL_AIS_END;

    // Backend AIS + attribution only. A failure or an empty result is shown
    // as exactly that — candidates are never invented, because a fabricated
    // ranking looks identical to a real one and would surface at the worst
    // possible moment: when the backend has actually computed nothing.
    setBacktrackStatusText("Scanning AIS traffic in the source region…");
    const vessels = await getCandidateVessels(bbox, start, end);
    if (runGenerationRef.current !== gen) return; // reset while in flight
    if (!vessels.length) {
      setTransposeNotice(describeEmptyMediterraneanAis());
      return;
    }

    setBacktrackStatusText("Ranking candidates…");
    const attribution = await runAttribution(
      CANONICAL_INCIDENT_ID,
      hc.source_region,
      vessels,
      10
    );
    if (runGenerationRef.current !== gen) return; // reset while in flight
    setAttributionResult(attribution);

    // Keep EVERY eligible candidate the backend returned: the counterfactual
    // engine must be able to test all of them, not an arbitrary top slice.
    const normalized = vesselsNearCentroid(
      normalizeVessels(vessels, attribution),
      { lat: slick.centroid.lat, lon: slick.centroid.lon }
    );
    if (normalized.length) {
      setBackendVessels(
        normalized.map((v) => ({ ...v, scoring: buildFrontendScoring(v) }))
      );
    }
    // Surface the engine's own caution flag instead of hiding it.
    setTransposeNotice(
      attribution?.no_strong_candidate
        ? "The attribution engine reports NO STRONG CANDIDATE — treat this ranking as weak supporting evidence only."
        : null
    );
  }, [backtrackResult, activeSlick]);

  // STAGE 3 — counterfactual forward test across EVERY eligible candidate.
  //
  // Each candidate is tested under TWO hypotheses, both run through the same
  // backend physics so the candidates stay comparable:
  //
  //   COMMON  — everyone released at the investigation's common release time
  //             (the start of the backend source-region window) from their
  //             OWN real AIS position at that instant. Same assumption for
  //             all, so the numbers compare directly.
  //   APPROVED— the backend attribution's own release state for that vessel
  //             (the moment it was actually inside the source region).
  //
  // Both matter: the common test is the controlled comparison, the approved
  // test is the hypothesis the attribution engine actually proposes. A
  // candidate with no AIS coverage at the release time is reported
  // unavailable — never given an invented position.
  const handleRunForwardStage = useCallback(async () => {
    const gen = runGenerationRef.current;
    const slick = activeSlick;
    const hc = backtrackResult?.backend;
    const candidates = scoredVessels;
    if (!slick || !candidates.length) return;

    const region = hc?.source_region?.candidate_regions?.[0];
    const commonReleaseMs = Date.parse(region?.start_time_utc || "");
    const observationIso = slick.timestamp_utc;
    const observationMs = Date.parse(observationIso);
    if (!Number.isFinite(observationMs)) return;
    const commonReleaseIso = Number.isFinite(commonReleaseMs)
      ? new Date(commonReleaseMs).toISOString()
      : null;

    const approvedByMmsi = new Map(
      (attributionResult?.top_candidates || []).map((c) => [String(c.vessel_mmsi), c])
    );

    const fwdMap = {};
    const cfMap = {};
    const commonMap = {};
    const notes = {};
    let firstOk = null;

    const runPair = async (mmsi, releaseLocation, releaseIso) => {
      const fwd = await runForwardSimulation({
        incident_id: CANONICAL_INCIDENT_ID,
        vessel_mmsi: mmsi,
        release_location: releaseLocation,
        release_time_utc: releaseIso,
        observation_time_utc: observationIso,
      });
      let cf = null;
      try {
        cf = await runCounterfactual(CANONICAL_INCIDENT_ID, mmsi, fwd, slick);
      } catch {
        /* comparison unavailable; the forward run still stands */
      }
      return { fwd, cf };
    };

    for (let i = 0; i < candidates.length; i++) {
      if (runGenerationRef.current !== gen) return; // reset mid-experiment
      const v = candidates[i];
      const mmsi = String(v.mmsi);
      setBacktrackStatusText(
        `Counterfactual test ${i + 1} / ${candidates.length} — ${v.name || mmsi}`
      );
      setCfProgress({ done: i, total: candidates.length });

      // 1) COMMON-TIME test from this vessel's own AIS position.
      const commonPos = commonReleaseIso ? aisPositionAt(v, commonReleaseMs) : null;
      if (commonPos) {
        try {
          const { cf } = await runPair(mmsi, commonPos, commonReleaseIso);
          if (cf) commonMap[mmsi] = cf;
        } catch {
          notes[mmsi] = "Common-time forward simulation unavailable.";
        }
      } else {
        notes[mmsi] = "No valid AIS release state at the common release time.";
      }

      // 2) The attribution's own approved release state, when it produced one.
      const approved = approvedByMmsi.get(mmsi);
      const approvedLoc = approved?.release_location;
      const approvedTime = approved?.release_time_utc;
      if (approvedLoc && approvedTime) {
        try {
          const { fwd, cf } = await runPair(mmsi, approvedLoc, approvedTime);
          fwdMap[mmsi] = fwd;
          if (cf) cfMap[mmsi] = cf;
          if (!firstOk) firstOk = mmsi;
        } catch {
          notes[mmsi] = "Forward simulation unavailable.";
        }
      } else if (!commonPos) {
        // already noted as unavailable
      } else if (!approved) {
        notes[mmsi] = notes[mmsi] || "No backend release state proposed for this vessel.";
      }
    }

    if (runGenerationRef.current !== gen) return;
    setCfProgress({ done: candidates.length, total: candidates.length });
    setForwardResults(fwdMap);
    setCounterfactualResults(cfMap);
    setCommonTestResults(commonMap);
    setCounterfactualNotes(notes);
    setCommonReleaseIso(commonReleaseIso);

    setBackendVessels((prev) =>
      (prev || [])
        .map((v) => {
          const cf = cfMap[String(v.mmsi)];
          if (!cf) return v;
          return {
            ...v,
            evidence: {
              ...v.evidence,
              drift: {
                score: Math.max(0, Math.min(1, +(cf.spatial_agreement || 0))),
                label:
                  cf.explanation ||
                  `Counterfactual: ${Math.round((cf.spatial_agreement || 0) * 100)}% spatial agreement.`,
              },
            },
          };
        })
        .map((v) => ({ ...v, scoring: buildFrontendScoring(v) }))
    );

    const selectedOk = selectedVesselId && fwdMap[String(selectedVesselId)];
    if (!selectedOk && firstOk) setSelectedVesselId(firstOk);

    const shown = fwdMap[String(selectedOk ? selectedVesselId : firstOk)];
    if (shown) {
      const relT = Date.parse(shown.release_time_utc);
      const ts = (shown.trajectory_timestamps_utc || [])
        .map((t) => Date.parse(t))
        .filter(Number.isFinite);
      const endT = ts.length ? Math.max(...ts) : observationMs;
      if (Number.isFinite(relT) && endT > relT) startPlayback(relT, endT);
    }
  }, [
    activeSlick,
    backtrackResult,
    attributionResult,
    scoredVessels,
    selectedVesselId,
    startPlayback,
  ]);

  // Which stage is next, derived from what the backend has produced so far.
  const pipelineStage = anyForward
    ? 3
    : attributionResult
      ? 2
      : backtrackResult?.backend
        ? 1
        : 0;
  const pipelineActionLabel = ["Run hindcast", "Run attribution", "Forward simulation", "Replay forward"][pipelineStage];

  // Clear every backend-derived result so the investigation can be run
  // again from the detection. Without this the pipeline is one-shot: the
  // hindcast can never be repeated and a stage that yields nothing usable
  // leaves the case stuck with no way back short of a page reload.
  // THE single authoritative reset for the whole investigation. It returns
  // the app to a fresh-load state, including the DETECTION stage, and bumps
  // a generation token so any request still in flight cannot repopulate the
  // UI after the reset (the stale-async repopulation bug).
  const handleResetInvestigation = useCallback(() => {
    // Bumping the generation is a deliberate event-handler side effect (not
    // a render-phase mutation): it invalidates any request still in flight.
    // eslint-disable-next-line react-hooks/immutability
    runGenerationRef.current += 1;

    // stop every animation / clock
    setIsPlaying(false);
    playPlanRef.current = null;
    setSimMs(NaN);
    setReplayProgress(0);

    // detection — this is what previously survived a reset
    setDetectionResult(null);
    setActiveSlick(null);
    setActiveSeedId(null);
    setApiSeedOverride(null);
    setIncident(INCIDENT_SEED);

    // hindcast / attribution / counterfactual
    setBacktrackResult(null);
    setAttributionResult(null);
    setForwardResults({});
    setCounterfactualResults({});
    setCommonTestResults({});
    setCommonReleaseIso(null);
    setCounterfactualNotes({});
    setCfProgress(null);
    setBackendVessels(null);
    setSelectedVesselId(null);

    // replay + status/UI
    setReplayMeta(null);
    setBackendError(null);
    setTransposeNotice(null);
    setBacktrackStatusText("");
    setIsBacktracking(false);
    setActiveItem("map");
  }, []);

  // One dispatcher keeps every existing button working: each press advances
  // the investigation by exactly one stage.
  const handleRunBacktrack = useCallback(async () => {
    if (isBacktracking) return;
    setIsBacktracking(true);
    setBackendError(null);
    try {
      if (pipelineStage === 0) await handleRunHindcastStage();
      else if (pipelineStage === 1) await handleRunAttributionStage();
      else if (pipelineStage === 2) await handleRunForwardStage();
      else {
        const relT = Date.parse(selectedForward?.release_time_utc || "");
        const fwdTs = (selectedForward?.trajectory_timestamps_utc || [])
          .map((t) => Date.parse(t))
          .filter(Number.isFinite);
        const endT = fwdTs.length ? Math.max(...fwdTs) : NaN;
        if (Number.isFinite(relT) && Number.isFinite(endT)) startPlayback(relT, endT);
      }
    } catch (err) {
      // describeHindcastFailure only recognises a few remote-forcing cases
      // and returns null otherwise (including for every local backend), so
      // fall back to the raw message — a failed stage must never be silent.
      const raw = err?.message || String(err);
      setBackendError(describeHindcastFailure(raw) || raw);
    } finally {
      setIsBacktracking(false);
      setBacktrackStatusText("");
    }
  }, [
    isBacktracking,
    pipelineStage,
    selectedForward,
    handleRunHindcastStage,
    handleRunAttributionStage,
    handleRunForwardStage,
    startPlayback,
  ]);

  /* =======================================================
     REPLAY POSITION & TRAJECTORY COMPUTATION
  ======================================================= */

  // Time-based interpolation along a vessel's AIS track (backend tracks
  // carry ISO timestamps); returns null when timestamps are unavailable.
  const timeReplayPosition = (vessel) => {
    if (!Number.isFinite(simMs)) return null;
    const tr = (vessel.trajectory || [])
      .map((pt) => ({ ...pt, ms: Date.parse(pt.time) }))
      .filter((pt) => Number.isFinite(pt.ms));
    if (tr.length < 2) return null;
    if (simMs <= tr[0].ms) return [tr[0].latitude, tr[0].longitude];
    const last = tr[tr.length - 1];
    if (simMs >= last.ms) return [last.latitude, last.longitude];
    let i = 1;
    while (i < tr.length && tr[i].ms < simMs) i++;
    const a = tr[i - 1], b = tr[i] || a;
    const f = b.ms === a.ms ? 0 : (simMs - a.ms) / (b.ms - a.ms);
    return [
      a.latitude + (b.latitude - a.latitude) * f,
      a.longitude + (b.longitude - a.longitude) * f,
    ];
  };

  // Vessel positions come ONLY from timestamped AIS data: at time T the
  // marker sits on the interpolation between the two surrounding AIS points.
  // Outside the vessel's own track the marker HOLDS at the nearest real
  // endpoint — movement is never invented from generic timeline progress.
  const getReplayPosition = (vessel) => {
    const timed = timeReplayPosition(vessel);
    if (timed) return timed;
    // No usable timestamped track: fall back to the vessel's last reported
    // AIS position as a static marker (no animation), or draw nothing.
    const lat = Number(vessel?.position?.latitude);
    const lon = Number(vessel?.position?.longitude);
    return Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : null;
  };

  const getReplayTrajectory = (vessel) => {
    const trajectory = vessel.trajectory || [];
    if (!trajectory.length) return [];
    // Every AIS point up to the current clock, plus the interpolated
    // current position. Purely timestamp-driven.
    const pts = trajectory
      .filter((pt) => {
        const ms = Date.parse(pt.time);
        return Number.isFinite(ms) && ms <= (Number.isFinite(simMs) ? simMs : Infinity);
      })
      .map((pt) => [pt.latitude, pt.longitude]);
    const cur = timeReplayPosition(vessel);
    if (cur) pts.push(cur);
    return pts;
  };

  // Vessels follow the master UTC clock whenever it has a value — there is
  // no separate "replay mode" clock and no progress-based fallback.
  const replayActive = Number.isFinite(simMs);

  // Estimated-release position within the simulation window (0..1).
  const releaseMs = selectedForward ? Date.parse(selectedForward.release_time_utc) : NaN;
  const releaseFrac =
    simRange && Number.isFinite(releaseMs)
      ? Math.max(0, Math.min(1, (releaseMs - simRange.t0) / (simRange.t1 - simRange.t0)))
      : null;

  // Adapters mapping the ReplayPanel's index-based API onto the master clock.
  const panelMaxP = Math.max(1, totalReplayPoints - 1);
  const panelProgress =
    simRange && Number.isFinite(simMs)
      ? ((simMs - simRange.t0) / (simRange.t1 - simRange.t0)) * panelMaxP
      : replayProgress;
  const setPanelProgress = (next) => {
    const value = typeof next === "function" ? next(panelProgress) : next;
    if (simRange) {
      setSimMs(simRange.t0 + (value / panelMaxP) * (simRange.t1 - simRange.t0));
    } else {
      setReplayProgress(value);
    }
  };

  /* =======================================================
     SELECTION & NAVIGATION
  ======================================================= */

  const handleSelectVessel = useCallback((vessel) => {
    if (!vessel) return;
    setSelectedVesselId(vessel.id);
    setActiveItem("vessels");
  }, []);

  const handleDeselect = useCallback(() => {
    setSelectedVesselId(null);
    setActiveItem((item) => (item === "vessels" ? "map" : item));
  }, []);

  const handleNavigation = (item) => {
    setActiveItem(item);
    if (["map", "incident", "vessels", "legend", "evidence", "tools", "replay", "detect"].includes(item)) {
      setIsPlaying(false);
    }
    if (item === "map") {
      setSelectedVesselId(null);
    }
  };

  const handleSpillClick = () => {
    handleDeselect();
  };

  const appThemeClass = "app-light";

  // The uncertainty circle is the backend hindcast's own estimate — its
  // centre, radius and confidence all come from /hindcast. Before the
  // hindcast runs there is no source region to draw.
  const activeSourceRegion = useMemo(() => {
    const sr = backtrackResult?.sourceRegion;
    if (!sr?.center || !Number.isFinite(Number(sr.center.latitude))) return null;
    return {
      center: sr.center,
      radiusMeters: Number(sr.radiusMeters) || 0,
      confidence: sr.confidence,
      type: "Estimated Source Region",
    };
  }, [backtrackResult]);

  const sourceCenter = activeSourceRegion
    ? [Number(activeSourceRegion.center.latitude), Number(activeSourceRegion.center.longitude)]
    : null;
  const sourceRadiusMeters = activeSourceRegion?.radiusMeters || 0;

  /* =======================================================
     RENDER (SINGLE MapContainer STRICTLY ENFORCED)
  ======================================================= */

  const showDetail = ["incident", "vessels", "legend", "replay", "evidence", "detect"].includes(activeItem);
  const closePanel = () => setActiveItem("map");
  const detectedMs = Date.parse(incident.detectedAt);
  const timelineEvents = (incident.timeline || []).map((event) => {
    const [hh, mm] = String(event.time).split(":").map(Number);
    const d = new Date(detectedMs);
    if (Number.isFinite(hh)) d.setUTCHours(hh, Number.isFinite(mm) ? mm : 0, 0, 0);
    return { ms: d.getTime(), label: event.label };
  });
  const clockStart = simRange?.t0 ?? Math.min(
    detectedMs - 6 * 60 * 60 * 1000,
    ...timelineEvents.map((event) => event.ms),
  );
  const clockEnd = simRange?.t1 ?? Math.max(detectedMs, ...timelineEvents.map((event) => event.ms));
  const clockNow = Number.isFinite(simMs)
    ? simMs
    : clockStart + Math.max(0, Math.min(1, replayProgress / Math.max(1, totalReplayPoints - 1))) * (clockEnd - clockStart);

  const seekClock = (ms) => {
    if (simRange) setSimMs(ms);
    else {
      const span = Math.max(1, clockEnd - clockStart);
      setReplayProgress(((ms - clockStart) / span) * Math.max(1, totalReplayPoints - 1));
    }
  };

  return (
    <div className={`app command-center ${appThemeClass}`}>
      <Sidebar
        activeItem={activeItem}
        layers={layers}
        onToggleLayer={toggleLayer}
        onSelect={handleNavigation}
        onTriggerBacktrack={handleRunBacktrack}
        backendOnline={backendOnline}
        backendHost={backendHost}
      />

      <div className="command-shell">
      <CommandTopBar
        incidentId={incident.id}
        search={queueQuery}
        onSearch={setQueueQuery}
        onNewIncident={() => setActiveItem("detect")}
      />
      <div className="command-body">
      <div className={`command-stage ${showDetail ? "is-detail" : ""}`}>
        <div className="command-stage-track">
          <div className="command-stage-pane">
            <InvestigationList
              incident={incident}
              vessels={scoredVessels}
              detectionCount={detectionResult?.features?.length || 0}
              selectedVesselId={selectedVesselId}
              onSelectVessel={handleSelectVessel}
              onOpenIncident={() => setActiveItem("incident")}
              onOpenDetect={() => setActiveItem("detect")}
              onRunHindcast={handleRunBacktrack}
              onResetInvestigation={handleResetInvestigation}
              isBacktracking={isBacktracking}
              actionLabel={pipelineActionLabel}
              pipelineStage={pipelineStage}
              hasDetection={hasDetection}
              counterfactualResults={counterfactualResults}
              commonTestResults={commonTestResults}
              commonReleaseIso={commonReleaseIso}
              counterfactualNotes={counterfactualNotes}
              cfProgress={cfProgress}
              backendOnline={backendOnline}
              backendHost={backendHost}
              query={queueQuery}
              onQueryChange={setQueueQuery}
            />
          </div>
          <div className="command-stage-pane command-detail">
              {activeItem === "incident" && (
                <IncidentPanel
                  incident={incident}
                  vessels={scoredVessels}
                  onSelectVessel={handleSelectVessel}
                  onClose={closePanel}
                  onTriggerBacktrack={handleRunBacktrack}
                  isBacktracking={isBacktracking}
                  actionLabel={pipelineActionLabel}
                />
              )}
              {activeItem === "vessels" && (
                <SuspectPanel
                  selectedVessel={selectedVessel}
                  allVessels={scoredVessels}
                  onSelectVessel={handleSelectVessel}
                  onClose={handleDeselect}
                  counterfactualResult={selectedCounterfactual}
                />
              )}
              {activeItem === "legend" && (
                <LegendPanel onClose={closePanel} />
              )}
              {activeItem === "replay" && (
                <ReplayPanel
                  vessels={scoredVessels}
                  isPlaying={isPlaying}
                  setIsPlaying={guardedSetIsPlaying}
                  replayProgress={panelProgress}
                  setReplayProgress={setPanelProgress}
                  replaySpeed={replaySpeed}
                  setReplaySpeed={setReplaySpeed}
                  totalPoints={totalReplayPoints}
                  timeLabel={simRange ? fmtSimClock(simMs ?? simRange.t1) : undefined}
                  startLabel={simRange
                    ? `${fmtSimClock(simRange.t0)} UTC`
                    : undefined}
                  endLabel={simRange
                    ? `${fmtSimClock(simRange.t1)} UTC`
                    : undefined}
                  releaseFrac={simRange ? releaseFrac : undefined}
                  forcingTag={simRange ? "OpenDrift forcing" : undefined}
                  currentFieldDesc={simRange ? "Ocean currents from backend forcing" : undefined}
                  windFieldDesc={simRange ? "Wind field from backend forcing" : undefined}
                  onClose={() => {
                    setIsPlaying(false);
                    closePanel();
                  }}
                />
              )}
              {activeItem === "evidence" && (
                <EvidencePanel
                  vessel={selectedVessel}
                  counterfactualResult={selectedCounterfactual}
                  onClose={() => setActiveItem(selectedVessel ? "vessels" : "map")}
                />
              )}
              {activeItem === "detect" && (
                <DetectionPanel
                  onDetectionResult={handleDetectionResult}
                  getRunGeneration={() => runGenerationRef.current}
                  onClose={closePanel}
                  onSeedOverride={handleSeedOverride}
                  onClearSeed={handleClearSeed}
                  activeSeedId={activeSeedId}
                  currentResult={detectionResult}
                />
              )}
          </div>
        </div>
      </div>

      <div className="command-workspace">
        <div className="command-workspace-main">
          <div className="command-map-wrap">
            <div className="map-floating-head">
              <div className="map-title-stack">
                <div className="map-title-chip">
                  <p className="inv-kicker">{incident.id}</p>
                  <h1>{incident.spillType}</h1>
                </div>
              </div>
              <div className="command-head-actions">
                <button
                  type="button"
                  className={`head-chip ${mapStyle === "map" ? "is-active" : ""}`}
                  onClick={() => setMapStyle("map")}
                >
                  Map
                </button>
                <button
                  type="button"
                  className={`head-chip ${mapStyle === "satellite" ? "is-active" : ""}`}
                  onClick={() => setMapStyle("satellite")}
                >
                  Satellite
                </button>
                <button type="button" className="head-chip" onClick={() => setActiveItem("legend")}>
                  Layers
                </button>
              </div>
            </div>
      <MapContainer
        center={[35.6353, 34.78]}
        zoom={10}
        zoomControl={false}
        className="map"
        preferCanvas={false}
        zoomAnimation={false}
        fadeAnimation={false}
        markerZoomAnimation={false}
        /* Calmer interaction: half-step zoom increments, a full wheel
           notch per half-step instead of Leaflet's touchy default, and a
           small debounce so trackpads don't jump several levels at once. */
        zoomSnap={0.5}
        zoomDelta={0.5}
        wheelPxPerZoomLevel={120}
        wheelDebounceTime={60}
      >
        <MapBackgroundClick onDeselect={handleDeselect} />

        {/* BASE MAP */}
        <TileLayer
          attribution={
            mapStyle === "satellite"
              ? "Tiles © Esri"
              : "© OpenStreetMap contributors"
          }
          url={
            mapStyle === "satellite"
              ? "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          }
          maxZoom={19}
        />

        {/* SIMULATED OCEAN CURRENT LAYER */}
        {/* OBSERVED SAR SLICK — static dark texture strictly inside the
            actual detection geometry. Never moves, fades, or recolors. */}
        {hasDetection && layers.spill && activeSlick?.geometry && (
          <DeckOilOverlay geometry={activeSlick.geometry} />
        )}

        {/* BACKEND RECONSTRUCTIONS — teal hindcast (stage 1, clock runs
            backward) / green forward drift (stage 3). Stage-scoped so only
            one reconstruction is ever on screen. The overlay's trail IS the
            single representative backend trajectory. */}
        <DriftCloudOverlay
          hindcast={backtrackResult?.backend}
          forward={selectedForward}
          slickGeometry={activeSlick?.geometry}
          stage={pipelineStage}
          timeMs={clockNow}
        />

        {/* OIL SPILL REGION (RED POLYGON) - Clean 6-sided polygon matching Screenshot 1 & 2 */}
        {hasDetection && layers.spill && spillPolygon.length >= 3 && (
          <Polygon
            positions={spillPolygon}
            pathOptions={{
              color: "#ef4444",
              weight: 2.5,
              opacity: 0.95,
              fillColor: "#ef4444",
              fillOpacity: 0.32,
              lineCap: "round",
              lineJoin: "round",
            }}
            eventHandlers={{ click: handleSpillClick }}
          >
            <Tooltip
              permanent
              direction="right"
              offset={[8, 0]}
              className="map-layer-label map-layer-label-slick"
            >
              OBSERVED SAR SLICK
            </Tooltip>
          </Polygon>
        )}

        {/* ESTIMATED SOURCE REGION (BLUE DASHED CIRCLE) - Encompasses the oil spill region */}
        {pipelineStage >= 1 && pipelineStage <= 2 && layers.sourceRegion && activeSourceRegion && sourceRadiusMeters > 0 && (
          <Circle
            center={sourceCenter}
            radius={sourceRadiusMeters}
            pathOptions={{
              color: "#3b82f6",
              weight: 2.5,
              opacity: 0.9,
              dashArray: "8 8",
              fillColor: "#3b82f6",
              fillOpacity: 0.04,
            }}
          >
            <Tooltip sticky direction="top">
              <strong>Estimated Source Region</strong>
              <br />
              Source: OpenDrift Lagrangian Hindcast
              <br />
              Centroid: {sourceCenter[0].toFixed(4)}°N, {sourceCenter[1].toFixed(4)}°E
              <br />
              Uncertainty Radius: {(sourceRadiusMeters / 1000).toFixed(2)} km
              {activeSourceRegion.confidence != null && (
                <>
                  <br />
                  Source-region probability mass: {activeSourceRegion.confidence}%
                </>
              )}
            </Tooltip>
          </Circle>
        )}

        {/* PREDICTED FOOTPRINT (GREEN) — forward simulation particle envelope */}
        {pipelineStage === 3 && predictedFootprintRing.length >= 3 && (
          <Polygon
            positions={predictedFootprintRing}
            pathOptions={{
              color: "#059669",
              weight: 2,
              opacity: 0.95,
              fillColor: "#10b981",
              fillOpacity: 0.2,
              lineCap: "round",
              lineJoin: "round",
            }}
          >
            <Tooltip sticky direction="top">
              <strong>Predicted footprint</strong>
              <br />
              Modelled forward-drift envelope — not an observed slick.
            </Tooltip>
          </Polygon>
        )}

        {/* ESTIMATED RELEASE POINT (RED) */}
        {pipelineStage === 3 && releasePoint && (
          <CircleMarker
            center={releasePoint.position}
            radius={6}
            pathOptions={{
              color: "#dc2626",
              weight: 3,
              fillColor: "#ffffff",
              fillOpacity: 1,
            }}
          >
            {/* Pinned only while the release point is the newest finding.
                Once the forward simulation runs, the plume needs that space,
                so the label drops back to hover. */}
            <Tooltip
              key={selectedForward ? "release-hover" : "release-pinned"}
              direction="right"
              offset={[10, 0]}
              permanent={!selectedForward}
            >
              <strong>Estimated release</strong>
              {releasePoint.time && (
                <>
                  <br />
                  {new Date(releasePoint.time).toISOString().replace("T", " ").substring(0, 16)} UTC
                </>
              )}
            </Tooltip>
          </CircleMarker>
        )}

        {/* HINDCAST BACKEND CANDIDATE REGIONS */}
        {pipelineStage >= 1 && pipelineStage <= 2 && layers.sourceRegion && candidateRegionsList.map((region) => (
          <Fragment key={region.id}>
            <Polygon
              positions={region.ring}
              pathOptions={{
                color: "#1d4ed8",
                weight: 2.2,
                opacity: 0.9,
                dashArray: "5 4",
                fillColor: "#3b82f6",
                fillOpacity: Math.min(0.22, Math.max(0.08, region.probability * 0.16)),
              }}
            >
              <Tooltip
                permanent
                direction="left"
                offset={[-8, 0]}
                className="map-layer-label map-layer-label-source"
              >
                PROBABLE SOURCE · KDE mass {(region.probability * 100).toFixed(0)}%
              </Tooltip>
            </Polygon>
            {region.centroid && (
              <CircleMarker
                center={region.centroid}
                radius={4.5}
                pathOptions={{
                  color: "#1e3a8a",
                  weight: 2,
                  fillColor: "#38bdf8",
                  fillOpacity: 0.95,
                }}
              >
                <Tooltip direction="top">
                  <strong>Candidate Centroid ({region.id})</strong>
                  <br />
                  {region.centroid[0].toFixed(4)}°N, {region.centroid[1].toFixed(4)}°E
                </Tooltip>
              </CircleMarker>
            )}
          </Fragment>
        ))}

        {/* OBSERVED SLICK CENTROID — from the detection response, distinct
            from the probable-source centroid and the estimated release. */}
        {hasDetection && layers.spill && observedCentroid && (
          <CircleMarker
            center={observedCentroid}
            radius={5}
            pathOptions={{
              color: "#b91c1c",
              weight: 2.5,
              fillColor: "#ffffff",
              fillOpacity: 1,
            }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              <strong>Observed slick centroid</strong>
              <br />
              {observedCentroid[0].toFixed(5)}°N, {observedCentroid[1].toFixed(5)}°E
            </Tooltip>
          </CircleMarker>
        )}

        {/* MAP TOOLBAR */}
        <MapToolbar
          onTriggerBacktrack={handleRunBacktrack}
          isBacktracking={isBacktracking}
          storyPoints={storyPoints}
          scenePoints={scenePoints}
          actionLabel={pipelineActionLabel}
        />

        {/* INITIAL MAP FIT */}
        <FitMapToIncident />
        <MapFill />

        {/* AUTO-REFIT + SOFT PAN BOUNDS AROUND THE INVESTIGATION */}
        <MapFocusController
          storyPoints={storyPoints}
          scenePoints={scenePoints}
          stageKey={focusStageKey}
        />

        {/* VESSELS + TRAJECTORIES */}
        {scoredVessels
          .filter((vessel) =>
            pipelineStage === 3 && selectedForward?.vessel_mmsi
              ? String(vessel.mmsi) === String(selectedForward.vessel_mmsi)
              : true
          )
          .map((vessel) => {
          const isSelected = selectedVesselId === vessel.id;
          const hasSelection = Boolean(selectedVesselId);
          const showVesselTooltip = !selectedVesselId;

          const normalTrajectory = (vessel.trajectory || []).map((point) => [
            Number(point.latitude),
            Number(point.longitude),
          ]);

          const replayTrajectory = getReplayTrajectory(vessel);
          const replayPosition = getReplayPosition(vessel);

          let polylineColor = "#94a3b8";
          let polylineWeight = 2;
          let polylineOpacity = 0.45;

          if (isSelected) {
            polylineColor = "#2563eb";
            polylineWeight = 5;
            polylineOpacity = 1;
          } else if (vessel.candidateRank === 1) {
            polylineColor = "#ea580c";
            polylineWeight = 3.5;
            polylineOpacity = hasSelection ? 0.75 : 0.95;
          } else if (hasSelection) {
            polylineColor = "#94a3b8";
            polylineWeight = 2;
            polylineOpacity = 0.18;
          }

          const handleVesselClick = (event) => {
            L.DomEvent.stopPropagation(event);
            if (event?.originalEvent) {
              L.DomEvent.stopPropagation(event.originalEvent);
            }
            handleSelectVessel(vessel);
          };

          return (
            <Fragment key={vessel.id}>
              {/* NORMAL TRAJECTORY */}
              {layers.trajectories && !replayActive && normalTrajectory.length >= 2 && (
                <>
                  {isSelected && (
                    <Polyline
                      positions={normalTrajectory}
                      pathOptions={{
                        color: "#60a5fa",
                        weight: 11,
                        opacity: 0.18,
                        lineCap: "round",
                        lineJoin: "round",
                      }}
                    />
                  )}
                  <Polyline
                    positions={normalTrajectory}
                    pathOptions={{
                      color: polylineColor,
                      weight: polylineWeight,
                      opacity: polylineOpacity,
                      lineCap: "round",
                      lineJoin: "round",
                    }}
                  />
                </>
              )}

              {/* REPLAY TRAJECTORY */}
              {layers.trajectories && replayActive && replayTrajectory.length >= 2 && (
                <>
                  {isSelected && (
                    <Polyline
                      positions={replayTrajectory}
                      pathOptions={{
                        color: "#60a5fa",
                        weight: 11,
                        opacity: 0.18,
                        lineCap: "round",
                        lineJoin: "round",
                      }}
                    />
                  )}
                  <Polyline
                    positions={replayTrajectory}
                    pathOptions={{
                      color: isSelected
                        ? "#2563eb"
                        : vessel.candidateRank === 1
                        ? "#ea580c"
                        : "#94a3b8",
                      weight: isSelected ? 5 : vessel.candidateRank === 1 ? 3 : 2,
                      opacity: isSelected ? 1 : vessel.candidateRank === 1 ? 0.9 : 0.5,
                      lineCap: "round",
                      lineJoin: "round",
                    }}
                  />
                </>
              )}

              {/* NORMAL VESSEL MARKER */}
              {layers.vessels && !replayActive && (
                <Marker
                  position={[
                    Number(vessel.position.latitude),
                    Number(vessel.position.longitude),
                  ]}
                  icon={createVesselIcon({
                    selected: isSelected,
                    candidateRank: vessel.candidateRank,
                    attributionConfidence: vessel.attributionConfidence,
                    name: vessel.name,
                    typeLabel: vesselTypeLabel(vessel),
                  })}
                  interactive
                  zIndexOffset={
                    isSelected
                      ? 1000
                      : vessel.candidateRank === 1
                      ? 200
                      : 0
                  }
                  eventHandlers={{ click: handleVesselClick }}
                >
                  <VesselPopup vessel={vessel} show={showVesselTooltip} />
                </Marker>
              )}

              {/* REPLAY VESSEL MARKER */}
              {layers.vessels && replayActive && (
                <Marker
                  position={replayPosition}
                  icon={createVesselIcon({
                    selected: isSelected,
                    replay: true,
                    candidateRank: vessel.candidateRank,
                    attributionConfidence: vessel.attributionConfidence,
                    name: vessel.name,
                    typeLabel: vesselTypeLabel(vessel),
                  })}
                  interactive
                  zIndexOffset={
                    isSelected
                      ? 1000
                      : vessel.candidateRank === 1
                      ? 200
                      : 0
                  }
                  eventHandlers={{ click: handleVesselClick }}
                >
                  <VesselPopup vessel={vessel} show={showVesselTooltip} />
                </Marker>
              )}
            </Fragment>
          );
        })}
      </MapContainer>

            {/* COMPACT MAP LEGEND — layer semantics only. Coordinates,
                area, confidence and evidence live in the side panels. */}
            {hasDetection && (
            <div className="map-key" aria-label="Map legend">
              {(
                <p className="map-key-line">
                  <span className="map-key-swatch" style={{ background: "rgba(239,68,68,0.3)", border: "1.5px solid #ef4444" }} />
                  Observed SAR slick
                </p>
              )}
              {pipelineStage >= 1 && (
                <p className="map-key-line">
                  <span className="map-key-swatch" style={{ background: "rgba(59,130,246,0.12)", border: "1.5px dashed #3b82f6" }} />
                  Probable source
                </p>
              )}
              {pipelineStage === 1 && (
                <p className="map-key-line">
                  <span className="map-key-dot" style={{ background: "#0db2c8" }} />
                  Backward reconstruction
                </p>
              )}
              {pipelineStage >= 2 && (
                <p className="map-key-line">
                  <span className="map-key-dot" style={{ background: "#2563eb" }} />
                  AIS candidate
                </p>
              )}
              {pipelineStage === 3 && (
                <>
                  <p className="map-key-line">
                    <span className="map-key-dot" style={{ background: "#ffffff", border: "2px solid #dc2626" }} />
                    Estimated release
                  </p>
                  <p className="map-key-line">
                    <span className="map-key-swatch" style={{ background: "rgba(16,185,129,0.2)", border: "1.5px solid #059669" }} />
                    Predicted footprint
                  </p>
                </>
              )}
            </div>
            )}

            <div className="command-ops-row">
              <OperationCard
                vessel={selectedVessel || topVessel}
                photoSrc="/vessels/mt-cyprus-sun.png"
                pipelineStage={pipelineStage}
              />
            </div>

            <TimelineControl
              startMs={clockStart}
              endMs={clockEnd}
              currentMs={clockNow}
              currentLat={incident.centroid.latitude}
              currentLng={incident.centroid.longitude}
              events={timelineEvents}
              isPlaying={isPlaying}
              onPlayPause={() => guardedSetIsPlaying((prev) => !prev)}
              playDisabled={!canReplay}
              onSeekMs={seekClock}
              playbackSpeed={replaySpeed}
              onSpeedChange={setReplaySpeed}
            />

            {isBacktracking && (
              <div className="run-card" role="status">
                <div className="run-card-head">
                  <strong>{["Hindcast", "Attribution", "Forward simulation", "Replay"][pipelineStage] || "Analysis"}</strong>
                  <span className="run-badge">Running</span>
                </div>
                <p>{backtrackStatusText || "Connecting…"}</p>
                <div className="run-rail" aria-hidden="true">
                  {["Hindcast", "AIS", "Rank", "Forward"].map((label, index) => (
                    <span
                      key={label}
                      className={index <= pipelineStepIndex(backtrackStatusText) ? "is-on" : ""}
                    >
                      {label}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {transposeNotice && !isBacktracking && (
              <div className="ops-toast warn">
                <strong>Note.</strong> {transposeNotice}
                <button type="button" onClick={() => setTransposeNotice(null)}>Dismiss</button>
              </div>
            )}

            {backendError && (
              <div className="ops-toast error">
                <strong>Request failed.</strong> {backendError}
                <button type="button" onClick={() => setBackendError(null)}>Dismiss</button>
              </div>
            )}

            <IntelRail
              incident={incident}
              vessels={scoredVessels}
              selectedVesselId={selectedVesselId}
              onSelectVessel={(id) => {
                const hit = scoredVessels.find(
                  (vessel) => String(vessel.id) === String(id) || String(vessel.mmsi) === String(id)
                );
                if (hit) handleSelectVessel(hit);
              }}
            />
          </div>
        </div>
      </div>
      </div>
      </div>
    </div>
  );
}

export default App;
