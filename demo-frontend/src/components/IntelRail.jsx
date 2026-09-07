import { useState } from "react";

function pct(value) {
  if (value == null) return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(100, n <= 1 ? Math.round(n * 100) : Math.round(n)));
}

function rankTone(value) {
  if (value == null) return "low";
  if (value >= 70) return "high";
  if (value >= 40) return "mid";
  return "low";
}

export default function IntelRail({
  vessels = [],
  onSelectVessel,
  selectedVesselId,
}) {
  const [envOpen, setEnvOpen] = useState(true);
  const [sourcesOpen, setSourcesOpen] = useState(true);

  const ranked = [...vessels].sort(
    (a, b) => (a.candidateRank || 99) - (b.candidateRank || 99)
  );

  return (
    <aside className="intel-rail" aria-label="Environmental conditions and sources">
      {/* No fabricated wind/current numbers: the API does not expose point
          samples of the forcing, so this card names the forcing datasets
          and says exactly that. */}
      <div className={`intel-card ${envOpen ? "is-open" : "is-collapsed"}`}>
        <button
          type="button"
          className="intel-accordion-trigger"
          onClick={() => setEnvOpen((prev) => !prev)}
          aria-expanded={envOpen}
        >
          <h3>Drift forcing</h3>
          <span className="intel-chevron" aria-hidden="true">{envOpen ? "−" : "+"}</span>
        </button>
        {envOpen && (
          <>
            <ul className="intel-env">
              <li>
                <span>Ocean currents</span>
                <strong>CMEMS Mediterranean</strong>
              </li>
              <li>
                <span>Wind</span>
                <strong>ERA5 · 10 m</strong>
              </li>
            </ul>
            <p className="intel-note">
              These NetCDF fields force the OpenDrift/OpenOil simulation on
              the backend. Point samples are not exposed by the current API,
              so no local values are shown.
            </p>
          </>
        )}
      </div>

      <div className={`intel-card ${sourcesOpen ? "is-open" : "is-collapsed"}`}>
        <button
          type="button"
          className="intel-accordion-trigger"
          onClick={() => setSourcesOpen((prev) => !prev)}
          aria-expanded={sourcesOpen}
        >
          <h3>Possible sources</h3>
          <span className="intel-chevron" aria-hidden="true">{sourcesOpen ? "−" : "+"}</span>
        </button>
        {sourcesOpen && (
          ranked.length ? (
            <ol className="intel-sources">
              {ranked.slice(0, 2).map((vessel) => {
                const score = pct(vessel.attributionConfidence);
                return (
                  <li key={vessel.id || vessel.mmsi}>
                    <button
                      type="button"
                      className={String(selectedVesselId) === String(vessel.id) ? "is-on" : ""}
                      onClick={() => onSelectVessel?.(vessel.id)}
                    >
                      <span>
                        <strong>{vessel.name || vessel.mmsi}</strong>
                        <em>{vessel.mmsi}</em>
                      </span>
                      <b className={rankTone(score)}>{score == null ? "—" : `${score}%`}</b>
                    </button>
                    <div className="intel-bar" aria-hidden="true">
                      <i className={rankTone(score)} style={{ width: `${score ?? 0}%` }} />
                    </div>
                  </li>
                );
              })}
            </ol>
          ) : (
            <p className="intel-empty">No AIS candidates yet — run attribution to scan traffic in the probable source region.</p>
          )
        )}
      </div>
    </aside>
  );
}
