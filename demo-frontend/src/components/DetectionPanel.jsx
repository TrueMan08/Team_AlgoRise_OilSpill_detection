/**
 * DetectionPanel.jsx
 *
 * Side panel for the OilTrace Detection Service API.
 * Manages its own local fetch state (idle → loading → success/error) and
 * communicates results upward via two callbacks:
 *   onDetectionResult(geojsonFeatureCollection)  — sets the map layer
 *   onSeedOverride({ lat, lon })                 — overrides backtrack seed
 *   onClearSeed()                                — clears seed override
 *   onClose()                                    — closes the panel
 *
 * Following the existing panel pattern this component is rendered in App.jsx
 * only when activeItem === "detect".
 */

import { useState, useRef, useCallback } from "react";
import {
  detectViaBackend,
  fetchDemoDetection,
  runLiveDetection,
} from "../services/detectionApi";
import incidentData from "../data/incident.json";
import { getReplay } from "../services/backendApi";
import "./DetectionPanel.css";

/**
 * Canonical demo detection.
 *
 * Geometry comes from the BACKEND: the observed slick polygon carried by the
 * replay frames of the canonical incident (the same geometry the pipeline
 * was validated against). The scene metadata (scene id, ML confidence, area,
 * observation time, centroid) comes from the canonical incident record —
 * those are the published facts of scene Oil/00067, not computed values.
 * The synthetic display hexagon is gone: what renders is the real footprint.
 */
async function canonicalMediterraneanDemo() {
  const inc = incidentData.incident;

  let geometry = null;
  try {
    const replay = await getReplay(inc.id);
    const framesWithSlick = (replay?.frames || []).filter(
      (f) => f?.slick?.geometry?.coordinates?.length
    );
    if (framesWithSlick.length) {
      // Latest frame = state at the observation time.
      geometry = framesWithSlick[framesWithSlick.length - 1].slick.geometry;
    }
  } catch {
    /* fall through to the canonical record's polygon */
  }

  if (!geometry) {
    // Offline fallback: the canonical record's own footprint ([lat, lon]
    // pairs in the incident file → GeoJSON [lon, lat]).
    const ring = (inc.spillPolygon || []).map(([lat, lon]) => [lon, lat]);
    if (ring.length && (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1])) {
      ring.push([...ring[0]]);
    }
    geometry = { type: "Polygon", coordinates: [ring] };
  }

  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: inc.id,
        properties: {
          id: inc.id,
          confidence: inc.detectionConfidence,
          area_km2: inc.areaKm2,
          centroid: { lat: inc.centroid.latitude, lon: inc.centroid.longitude },
          timestamp_utc: inc.detectedAt,
          sensor: inc.satellite?.sensor || "SAR",
          scene_id: inc.satellite?.imageId || "Oil/00067",
        },
        geometry,
      },
    ],
  };
}

/* ── Confidence badge helper ─────────────────────────────── */
function ConfidenceBadge({ confidence }) {
  const pct = Math.round(confidence * 100);
  const isSolid = confidence >= 0.75;
  return (
    <span
      className={`detection-confidence-badge ${
        isSolid ? "detection-confidence-solid" : "detection-confidence-uncertain"
      }`}
    >
      {isSolid ? "●" : "◐"} {pct}%{" "}
      {!isSolid && <em style={{ fontStyle: "normal", opacity: 0.75 }}>uncertain</em>}
    </span>
  );
}

/* ── Single slick card ───────────────────────────────────── */
function SlickCard({ feature, activeSeedId, onUseSeed }) {
  const { id, confidence, area_km2, centroid } = feature.properties;
  const isActiveSeed = activeSeedId === id;

  const handleSeed = () => {
    onUseSeed({ lat: centroid.lat, lon: centroid.lon }, id);
  };

  return (
    <div className="detection-slick-card">
      <div className="detection-slick-header">
        <span className="detection-slick-id">{id}</span>
        <ConfidenceBadge confidence={confidence} />
      </div>

      <div className="detection-slick-metrics">
        <div className="detection-slick-metric">
          <strong>{area_km2.toFixed(1)} km²</strong>
          Area (UTM)
        </div>
        <div className="detection-slick-metric">
          <strong>{Math.round(confidence * 100)}%</strong>
          Confidence
        </div>
      </div>

      <div className="detection-slick-coords">
        {centroid.lat.toFixed(5)}°N {centroid.lon.toFixed(5)}°E
      </div>

      <button
        type="button"
        className={`detection-seed-button ${isActiveSeed ? "is-active-seed" : ""}`}
        onClick={handleSeed}
        title="Use this slick centroid as the backtrack starting point"
      >
        <span>↺</span>
        {isActiveSeed ? "Active backtrack seed" : "Use as backtrack seed"}
      </button>
    </div>
  );
}

/* ── Main panel ──────────────────────────────────────────── */
export function DetectionPanel({
  onDetectionResult,
  getRunGeneration,
  onClose,
  onSeedOverride,
  onClearSeed,
  activeSeedId,
  currentResult,
}) {
  // status: 'idle' | 'loading-demo' | 'loading-live' | 'success' | 'error'
  const [status, setStatus] = useState(currentResult ? "success" : "idle");
  const [result, setResult] = useState(currentResult ?? null);
  const [error, setError] = useState(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadedFileName, setUploadedFileName] = useState(null);

  const fileInputRef = useRef(null);

  /* ── Demo fetch ─────────────────────────────────────── */
  const handleLoadDemo = useCallback(async () => {
    const gen = getRunGeneration?.();
    setStatus("loading-demo");
    setError(null);
    try {
      if (import.meta.env.VITE_USE_MODAL_ML !== "true") {
        const geojson = await canonicalMediterraneanDemo();
        setResult(geojson);
        setStatus("success");
        onDetectionResult(geojson, gen);
        return;
      }
      const geojson = await fetchDemoDetection();
      setResult(geojson);
      setStatus("success");
      onDetectionResult(geojson, gen);
    } catch (err) {
      setError(err.message || "Failed to load demo detection.");
      setStatus("error");
    }
  }, [onDetectionResult, getRunGeneration]);

  /* ── Live inference ─────────────────────────────────── */
  const handleFile = useCallback(
    async (file) => {
      if (!file) return;
      const gen = getRunGeneration?.();
      setUploadedFileName(file.name);
      setStatus("loading-live");
      setError(null);
      try {
        let geojson;
        try {
          geojson = await detectViaBackend(file);
        } catch (backendError) {
          if (import.meta.env.VITE_USE_MODAL_ML === "true") {
            geojson = await runLiveDetection(file);
          } else {
            throw backendError;
          }
        }
        setResult(geojson);
        setStatus("success");
        onDetectionResult(geojson, gen);
      } catch (err) {
        setError(err.message || "Detection failed. Please try again.");
        setStatus("error");
      }
    },
    [onDetectionResult, getRunGeneration]
  );

  const handleInputChange = (e) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    // reset so same file can be re-selected
    e.target.value = "";
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  /* ── Reset to idle ─────────────────────────────────── */
  const handleReset = () => {
    setStatus("idle");
    setResult(null);
    setError(null);
    setUploadedFileName(null);
  };

  /* ── Feature helpers ────────────────────────────────── */
  const features = result?.features ?? [];
  const props = result?.properties ?? {};
  const model = props.model ?? {};
  const inferenceS = props.inference_seconds;
  const threshold = props.threshold;

  const isLoading = status === "loading-demo" || status === "loading-live";

  return (
    <aside
      className="oiltrace-context-panel detection-panel"
      aria-label="Detection service panel"
    >
      {/* ── HEADER ─────────────────────────────────────── */}
      <div className="context-panel-header detection-panel-header">
        <div>
          <h2 className="detection-panel-title">Oil Detection</h2>
          <p className="detection-panel-subtitle">
            Sentinel-1 VV+VH → U-Net → GeoJSON slick polygons
          </p>
        </div>

        <button
          type="button"
          className="context-close-button"
          onClick={onClose}
          aria-label="Close detection panel"
        >
          ×
        </button>
      </div>

      {/* ── SEED OVERRIDE BANNER ─────────────────────────── */}
      {activeSeedId && (
        <div className="detection-seed-banner">
          <span className="detection-seed-banner-text">
            ↺ Backtrack seeded from <strong>{activeSeedId}</strong>
          </span>
          <button
            type="button"
            className="detection-seed-clear-btn"
            onClick={onClearSeed}
          >
            Clear
          </button>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════
          IDLE STATE
      ═══════════════════════════════════════════════════ */}
      {status === "idle" && (
        <>
          <div className="detection-intro-card">
            <span className="detection-intro-icon">SAR</span>
            <p className="detection-intro-text">
              Load the pre-computed demo scene (Eastern Mediterranean, 267 km²
              slick) for an instant result, or upload your own Sentinel-1
              GeoTIFF for live inference.
            </p>
          </div>

          <button
            type="button"
            className="detection-demo-button"
            onClick={handleLoadDemo}
            id="detection-load-demo-btn"
          >
            <span>🌍</span>
            Load Demo Detection
          </button>

          <div className="detection-section">
            <span className="detection-section-label">Live Inference</span>

            {/* Drop zone */}
            <div
              className={`detection-upload-zone ${isDragOver ? "drag-over" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={handleDrop}
              id="detection-upload-zone"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".tif,.tiff"
                onChange={handleInputChange}
                aria-label="Upload GeoTIFF scene"
              />
              <span className="detection-upload-icon">TIFF</span>
              <p className="detection-upload-title">Drop GeoTIFF here</p>
              <p className="detection-upload-hint">
                2-band VV+VH · georeferenced · ≤ 80 MB
                <br />
                or click to browse
              </p>
            </div>
          </div>
        </>
      )}

      {/* ═══════════════════════════════════════════════════
          LOADING STATE
      ═══════════════════════════════════════════════════ */}
      {isLoading && (
        <div className="detection-loading-wrap">
          <div className="detection-loading-header">
            <div className="detection-spinner" />
            <span className="detection-loading-label">
              {status === "loading-demo"
                ? "Fetching demo scene…"
                : "Running inference…"}
            </span>
          </div>

          {status === "loading-live" && (
            <p className="detection-loading-sub">
              Tiled U-Net inference on CPU takes 20–60 s per 2048² scene.
              {uploadedFileName && (
                <>
                  <br />
                  <strong>{uploadedFileName}</strong>
                </>
              )}
            </p>
          )}

          <div className="detection-loading-steps">
            {(status === "loading-live"
              ? [
                  "Uploading scene to inference service",
                  "Tiling scene into 512² patches",
                  "Running U-Net forward pass (CPU)",
                  "Stitching probability map",
                  "Thresholding & vectorising polygons",
                ]
              : ["Fetching cached demo result", "Parsing GeoJSON response"]
            ).map((step, i) => (
              <div key={step} className="detection-loading-step" style={{ opacity: 0.55 + i * 0.09 }}>
                <div className="detection-step-dot" />
                <span>{step}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════
          ERROR STATE
      ═══════════════════════════════════════════════════ */}
      {status === "error" && (
        <div className="detection-error-card">
          <p className="detection-error-title">⚠ Detection Error</p>
          <p className="detection-error-message">{error}</p>
          <button
            type="button"
            className="detection-retry-button"
            onClick={handleReset}
          >
            ↩ Try Again
          </button>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════
          SUCCESS STATE
      ═══════════════════════════════════════════════════ */}
      {status === "success" && result && (
        <>
          {/* Model + inference metadata */}
          <div className="detection-model-badge">
            <strong>{model.name ?? "OilTrace-U-Net"}</strong>
            <span>·</span>
            <span>exp: {model.experiment ?? "—"}</span>
            <span>·</span>
            <span>epoch {model.checkpoint_epoch ?? "—"}</span>
            {inferenceS != null && (
              <>
                <span>·</span>
                <span>{inferenceS.toFixed(1)} s</span>
              </>
            )}
          </div>

          {/* Inference stats pills */}
          <div className="detection-stats-strip">
            <span className="detection-stat-pill">
              <strong>{features.length}</strong>&nbsp;slick{features.length !== 1 ? "s" : ""}&nbsp;detected
            </span>
            {threshold != null && (
              <span className="detection-stat-pill">
                threshold: <strong>{threshold}</strong>
              </span>
            )}
            {props.scene_id && (
              <span className="detection-stat-pill">
                scene: <strong>{props.scene_id}</strong>
              </span>
            )}
          </div>

          {/* No slick case */}
          {features.length === 0 ? (
            <div className="detection-empty-card">
              <span className="detection-empty-icon">0</span>
              <p className="detection-empty-text">
                No oil slicks detected in this scene. An empty result on clean
                water is a valid, common outcome.
              </p>
            </div>
          ) : (
            <>
              <span className="detection-section-label">
                Detected Slicks — largest first
              </span>
              <div className="detection-slick-list">
                {features.map((feature) => (
                  <SlickCard
                    key={feature.properties.id}
                    feature={feature}
                    activeSeedId={activeSeedId}
                    onUseSeed={onSeedOverride}
                  />
                ))}
              </div>
            </>
          )}

          {/* New scene upload */}
          <button
            type="button"
            className="detection-upload-another"
            onClick={handleReset}
            id="detection-upload-another-btn"
          >
            <span>📂</span> Upload another scene
          </button>
        </>
      )}
    </aside>
  );
}

export default DetectionPanel;
