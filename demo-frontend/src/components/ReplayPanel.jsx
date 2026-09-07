import { useMemo } from "react";
import "./ReplayPanel.css";

function ReplayPanel({
  vessels = [],
  onClose,
  isPlaying = false,
  setIsPlaying,
  replayProgress = 0,
  setReplayProgress,
  replaySpeed = 1,
  setReplaySpeed,
  totalPoints = 1,
  timeLabel,
  currentFieldDesc = "SIMULATED CURRENT (WESTWARD 0.3 m/s)",
  windFieldDesc = "SIMULATED WIND (NNW 5.2 m/s)",
  startLabel = "Start",
  endLabel = "End",
  forcingTag = "SIMULATED",
  releaseFrac,
}) {
  const maxProgress = Math.max(1, totalPoints - 1);
  const normalizedProgress = Math.max(0, Math.min(replayProgress, maxProgress));
  const progressPercent = (normalizedProgress / maxProgress) * 100;

  const computedTime = useMemo(() => timeLabel || "—", [timeLabel]);

  const togglePlaying = () => {
    if (normalizedProgress >= maxProgress) {
      setReplayProgress?.(0);
      setIsPlaying?.(true);
      return;
    }

    setIsPlaying?.((current) => !current);
  };

  const resetReplay = () => {
    setIsPlaying?.(false);
    setReplayProgress?.(0);
  };

  const handleSliderChange = (event) => {
    const nextProgress = Number(event.target.value);
    setIsPlaying?.(false);
    setReplayProgress?.(nextProgress);
  };

  return (
    <aside className="oiltrace-replay-panel">
      <div className="replay-panel-header">
        <div>
          <span className="replay-kicker">TEMPORAL ANALYSIS</span>
          <h2>Replay & Transport</h2>
          <p>Reconstruct vessel tracks & time-dependent oil drift over time.</p>
        </div>

        <button
          className="replay-close"
          type="button"
          onClick={onClose}
          aria-label="Close replay"
        >
          ×
        </button>
      </div>

      <div className="replay-time-card">
        <div className="replay-current-time">
          <span className="replay-time-label">SCENE CLOCK</span>
          <strong>{computedTime} UTC</strong>
        </div>

        <div className="replay-status">
          <span className={`replay-status-dot ${isPlaying ? "playing" : ""}`} />
          {isPlaying ? "Playing" : "Paused"}
        </div>
      </div>

      <div className="replay-timeline-section">
        <div className="replay-timeline-labels">
          <span>{startLabel}</span>
          <span>{endLabel}</span>
        </div>

        <div style={{ position: "relative" }}>
          <input
            className="replay-slider"
            type="range"
            min={0}
            max={maxProgress}
            step={0.01}
            value={normalizedProgress}
            style={{
              "--replay-progress": `${progressPercent}%`,
            }}
            onChange={handleSliderChange}
            aria-label="Replay timeline"
          />
          {/* Release tick at its true position on the timeline */}
          {releaseFrac !== undefined &&
            releaseFrac !== null &&
            releaseFrac > 0.03 &&
            releaseFrac < 0.97 && (
              <div
                style={{
                  position: "absolute",
                  left: `${releaseFrac * 100}%`,
                  top: "-2px",
                  transform: "translateX(-50%)",
                  width: "2px",
                  height: "16px",
                  background: "#2563eb",
                  borderRadius: "1px",
                  pointerEvents: "none",
                }}
              />
            )}
        </div>
      </div>

      <div className="replay-controls">
        <button
          type="button"
          className="replay-reset-button"
          onClick={resetReplay}
          title="Reset replay"
          aria-label="Reset replay"
        >
          ↻
        </button>

        <button
          type="button"
          className="replay-play-button"
          onClick={togglePlaying}
          title={isPlaying ? "Pause replay" : "Play replay"}
          aria-label={isPlaying ? "Pause replay" : "Play replay"}
        >
          {isPlaying ? "Ⅱ" : "▶"}
        </button>
      </div>

      <div className="replay-speed-section">
        <div className="replay-speed-heading">
          <span className="replay-speed-title">Playback Speed</span>
        </div>

        <div className="replay-speed-buttons">
          {[0.5, 1, 2, 4].map((value) => (
            <button
              key={value}
              type="button"
              className={`speed-button ${replaySpeed === value ? "active" : ""}`}
              onClick={() => setReplaySpeed?.(value)}
            >
              {value}×
            </button>
          ))}
        </div>
      </div>

      {/* METEOROLOGICAL & CURRENT DRIFT FACTORS */}
      <div className="replay-vessel-summary" style={{ marginBottom: "1rem" }}>
        <div className="replay-summary-header">
          <span>DRIFT FORCING FIELDS</span>
          <span className="demo-text" style={{ fontSize: "0.7rem", opacity: 0.8 }}>{forcingTag}</span>
        </div>

        <div className="replay-vessel-row" style={{ fontSize: "0.78rem" }}>
          <span className="replay-vessel-num">1</span>
          <span className="replay-vessel-name">{currentFieldDesc}</span>
        </div>

        <div className="replay-vessel-row" style={{ fontSize: "0.78rem" }}>
          <span className="replay-vessel-num">2</span>
          <span className="replay-vessel-name">{windFieldDesc}</span>
        </div>
      </div>

      <div className="replay-vessel-summary">
        <div className="replay-summary-header">
          <span>VESSEL TRACKS</span>
          <strong>{vessels.length}</strong>
        </div>

        {vessels.length > 0 ? (
          vessels.slice(0, 6).map((vessel, index) => (
            <div className="replay-vessel-row" key={vessel.id}>
              <span className="replay-vessel-num">{vessel.candidateRank || index + 1}</span>
              <span className="replay-vessel-name">{vessel.name}</span>
              <span className="replay-vessel-rank">#{vessel.candidateRank}</span>
            </div>
          ))
        ) : (
          <div className="replay-empty">No vessel tracks available.</div>
        )}
      </div>

      <div className="replay-analysis-note">
        <span className="replay-note-icon">i</span>
        <p>
          Replay reconstructs vessel movement alongside particle drift.
          Ocean current and wind vectors drive the modelled oil transport.
        </p>
      </div>
    </aside>
  );
}

export default ReplayPanel;