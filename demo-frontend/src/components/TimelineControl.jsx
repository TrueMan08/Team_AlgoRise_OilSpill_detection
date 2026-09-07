import "./TimelineControl.css";

function formatClock(ms, withDate = true) {
  if (!Number.isFinite(ms)) return "—";
  const d = new Date(ms);
  const time = d.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });
  if (!withDate) return `${time} UTC`;
  const date = d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
  return `${date} · ${time} UTC`;
}

export function TimelineControl({
  startMs,
  endMs,
  currentMs,
  currentLat,
  currentLng,
  events = [],
  isPlaying = false,
  onPlayPause,
  playDisabled = false,
  onSeekMs,
  playbackSpeed = 1,
  onSpeedChange,
}) {
  const span = Math.max(1, (endMs || 0) - (startMs || 0));
  const now = Number.isFinite(currentMs) ? currentMs : endMs;
  const progress = Math.max(0, Math.min(1, (now - startMs) / span));
  const currentEvent = events.find((event) => {
    const dist = Math.abs(event.ms - now);
    return dist <= span * 0.06;
  });

  const handleSeek = (event) => {
    const next = startMs + Number(event.target.value) * span;
    onSeekMs?.(next);
  };

  const coordStr =
    Number.isFinite(currentLat) && Number.isFinite(currentLng)
      ? `${Math.abs(currentLat).toFixed(3)}°${currentLat >= 0 ? "N" : "S"} ${Math.abs(currentLng).toFixed(3)}°${currentLng >= 0 ? "E" : "W"}`
      : null;

  return (
    <div className="timeline-card" role="region" aria-label="Transport timeline">
      <div className="timeline-header">
        <div className="timeline-status-group">
          {currentEvent && (
            <span className="timeline-event-chip">{currentEvent.label}</span>
          )}
          {coordStr && (
            <span className="timeline-coord-badge">{coordStr}</span>
          )}
        </div>

        <strong className="timestamp-text">{formatClock(now)}</strong>

        <div className="speed-toggle-group">
          {[1, 2, 4].map((speed) => (
            <button
              key={speed}
              type="button"
              className={`speed-btn ${playbackSpeed === speed ? "active" : ""}`}
              onClick={() => onSpeedChange?.(speed)}
            >
              {speed}x
            </button>
          ))}
        </div>
      </div>

      <div className="slider-wrapper">
        <span className="time-endpoint-label start">{formatClock(startMs)}</span>
        <div className="slider-track-container">
          <div className="slider-rail" />
          <div className="slider-progress-fill" style={{ width: `${progress * 100}%` }} />
          {events.map((event) => {
            const left = Math.max(0, Math.min(100, ((event.ms - startMs) / span) * 100));
            return (
              <button
                key={`${event.ms}-${event.label}`}
                type="button"
                className="tick-point has-event"
                style={{ left: `${left}%` }}
                title={`${formatClock(event.ms)} · ${event.label}`}
                onClick={() => onSeekMs?.(event.ms)}
              >
                <span className="tick-dot" />
              </button>
            );
          })}
          <input
            type="range"
            min={0}
            max={1}
            step={0.002}
            value={progress}
            onChange={handleSeek}
            className="time-slider"
            aria-label="Transport time"
          />
        </div>
        <span className="time-endpoint-label end">{formatClock(endMs)}</span>
      </div>

      <div className="timeline-footer">
        <div className="playback-controls">
          <button
            type="button"
            className="control-btn step-btn"
            onClick={() => onSeekMs?.(Math.max(startMs, now - span * 0.05))}
            aria-label="Step back"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M15.5 7 10 12l5.5 5" />
              <path d="M8 7v10" />
            </svg>
          </button>
          <button
            type="button"
            className={`control-btn play-pause-btn ${isPlaying ? "is-playing" : ""}`}
            onClick={onPlayPause}
            disabled={playDisabled}
            title={playDisabled ? "Run hindcast to enable replay" : undefined}
            style={playDisabled ? { opacity: 0.45, cursor: "not-allowed" } : undefined}
          >
            {isPlaying ? (
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 7h3v10H8zM13 7h3v10h-3z" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M9 7.5v9l8-4.5z" />
              </svg>
            )}
            <span>{isPlaying ? "Pause" : "Play"}</span>
          </button>
          <button
            type="button"
            className="control-btn step-btn"
            onClick={() => onSeekMs?.(Math.min(endMs, now + span * 0.05))}
            aria-label="Step forward"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m8.5 7 5.5 5-5.5 5" />
              <path d="M16 7v10" />
            </svg>
          </button>
        </div>
        <div className="timeline-counter">
          {events.map((event) => (
            <span key={event.label}>{event.label}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
