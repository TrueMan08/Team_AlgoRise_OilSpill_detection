import { useMemo, useState } from "react";
import "./InvestigationList.css";

function confidencePct(value) {
  if (value == null) return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(100, n <= 1 ? Math.round(n * 100) : Math.round(n)));
}

function statusClass(pct) {
  if (pct == null) return "delivered";
  if (pct >= 70) return "in-transit";
  if (pct >= 40) return "queued";
  return "delivered";
}

const WORKFLOW_STEPS = [
  { id: "detect", num: "01", label: "Detection", hint: "SAR oil slick" },
  { id: "hindcast", num: "02", label: "Hindcast", hint: "Backtrack source" },
  { id: "attribution", num: "03", label: "Attribution", hint: "Rank vessels" },
  { id: "forward", num: "04", label: "Forward", hint: "Counterfactual" },
];

export default function InvestigationList({
  vessels = [],
  selectedVesselId,
  onSelectVessel,
  onOpenDetect,
  onRunHindcast,
  onResetInvestigation,
  isBacktracking = false,
  actionLabel = "Run hindcast",
  pipelineStage = 0,
  hasDetection = false,
  counterfactualResults = {},
  commonTestResults = {},
  commonReleaseIso,
  counterfactualNotes = {},
  cfProgress,
  backendOnline,
  backendHost,
  query: queryProp,
  onQueryChange,
}) {
  const [queryLocal, setQueryLocal] = useState("");
  const query = queryProp ?? queryLocal;
  const setQuery = onQueryChange || setQueryLocal;
  const [filter] = useState("all");

  const ranked = useMemo(
    () => [...vessels].sort((a, b) => (a.candidateRank || 99) - (b.candidateRank || 99)),
    [vessels]
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return ranked.filter((v) => {
      const pct = confidencePct(v.attributionConfidence);
      if (filter === "ranked" && (pct ?? 0) < 40) return false;
      if (filter === "high" && (pct ?? 0) < 70) return false;
      if (!q) return true;
      return [v.name, v.id, v.mmsi, v.type, v.flag]
        .filter(Boolean)
        .some((part) => String(part).toLowerCase().includes(q));
    });
  }, [ranked, query, filter]);

  const isLocal = /localhost|127\.0\.0\.1/i.test(String(backendHost || ""));
  const linkLabel =
    backendOnline === true
      ? isLocal
        ? "Local"
        : "Live"
      : backendOnline === false
        ? isLocal
          ? "Local offline"
          : "Offline"
        : "Checking";

  return (
    <section className="inv-list" aria-label="Investigation queue">
      <header className="inv-list-header">
        <div>
          <p className="inv-kicker">Case queue</p>
          <h2>Tracking slicks</h2>
        </div>
        <span className={`inv-link-chip ${backendOnline === true ? "ok" : backendOnline === false ? "bad" : "wait"}`}>
          {linkLabel}
        </span>
      </header>

      {/* Investigation workflow — the operator can always see which stage the
          case has reached and what the next action produces. */}
      <ol className="inv-workflow" aria-label="Investigation workflow">
        {WORKFLOW_STEPS.map((step, index) => {
          // Step 01 is complete once a detection is loaded; steps 02-04 map
          // onto pipelineStage 1-3.
          const done = index === 0 ? hasDetection : pipelineStage >= index;
          const isActive =
            index === 0 ? !hasDetection : hasDetection && pipelineStage === index - 1;
          return (
            <li
              key={step.id}
              className={`inv-step ${done ? "is-done" : ""} ${isActive && !done ? "is-active" : ""}`}
            >
              <span className="inv-step-num" aria-hidden="true">
                {done ? "✓" : step.num}
              </span>
              <span className="inv-step-text">
                <strong>{step.label}</strong>
                <small>{step.hint}</small>
              </span>
            </li>
          );
        })}
      </ol>

      {/* COUNTERFACTUAL COMPARISON — this list owns the at-a-glance
          comparison across candidates; the selected vessel's full reasoning
          lives in the vessel panel, not here. All values are the backend's. */}
      {(cfProgress || Object.keys(counterfactualResults).length > 0) && (
        <div className="inv-cf-panel">
          <p className="inv-cf-head">
            Counterfactual forward test
            {cfProgress && (
              <span className="inv-cf-progress">
                {cfProgress.done} / {cfProgress.total} tested
              </span>
            )}
          </p>

          <div className="inv-cf-table" role="table">
            <div className="inv-cf-tr inv-cf-th" role="row">
              <span>Candidate</span>
              <span>Attr.</span>
              <span>In slick</span>
              <span>Offset</span>
            </div>
            {ranked.map((v) => {
              const key = String(v.mmsi);
              const cf = counterfactualResults[key];
              const common = commonTestResults[key];
              const note = counterfactualNotes[key];
              const attr = confidencePct(v.attributionConfidence);
              const pctIn = (r) =>
                r?.predicted_containment != null
                  ? Math.round(r.predicted_containment * 100)
                  : r?.spatial_agreement != null
                    ? Math.round(r.spatial_agreement * 100)
                    : null;
              return (
                <button
                  key={key}
                  type="button"
                  role="row"
                  className={`inv-cf-tr ${String(selectedVesselId) === key ? "is-on" : ""}`}
                  onClick={() => onSelectVessel?.(v)}
                >
                  <span className="inv-cf-name">{v.name || key}</span>
                  <span>{attr != null ? `${attr}%` : "—"}</span>
                  {cf ? (
                    <>
                      <span className={cf.trajectory_reaches_slick ? "is-yes" : ""}>
                        {pctIn(cf) != null ? `${pctIn(cf)}%` : "—"}
                      </span>
                      <span>
                        {cf.centroid_distance_km != null
                          ? `${Number(cf.centroid_distance_km).toFixed(1)} km`
                          : "—"}
                      </span>
                    </>
                  ) : (
                    <span className="inv-cf-span2">
                      {note ? "Unavailable" : "Not tested"}
                    </span>
                  )}
                  {(note || common) && (
                    <span className="inv-cf-sub">
                      {note ||
                        `Common-time sensitivity test ${commonReleaseIso ? commonReleaseIso.substring(11, 16) + "Z" : ""}: ${pctIn(common)}% in slick, ${common.trajectory_reaches_slick ? "reaches" : "misses"}`}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          <p className="inv-cf-foot">
            Candidate-specific test uses each vessel&apos;s attributed release
            state. Supports physical consistency; does not prove responsibility.
          </p>
        </div>
      )}

      <div className="inv-search">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search MMSI, name, type"
          aria-label="Search vessels"
        />
      </div>


      <div className="inv-actions">
        <button type="button" className="inv-action primary" onClick={onRunHindcast} disabled={isBacktracking}>
          {isBacktracking ? "Running…" : actionLabel}
        </button>
        {pipelineStage > 0 && onResetInvestigation ? (
          <button
            type="button"
            className="inv-action"
            onClick={onResetInvestigation}
            title="Clear all analysis results and start again from the detection"
          >
            Reset analysis
          </button>
        ) : (
          <button type="button" className="inv-action" onClick={onOpenDetect}>
            SAR detect
          </button>
        )}
      </div>

      {ranked[0] && (
        <div className="inv-top-hit">
          <div>
            <p>{confidencePct(ranked[0].attributionConfidence) == null ? "Nearby vessel" : "Top candidate"}</p>
            <strong>{ranked[0].name || ranked[0].mmsi}</strong>
          </div>
          <button type="button" className="inv-action" onClick={() => onSelectVessel?.(ranked[0])}>
            {confidencePct(ranked[0].attributionConfidence) == null
              ? "inspect"
              : `${confidencePct(ranked[0].attributionConfidence)}% inspect`}
          </button>
        </div>
      )}

      <div className="inv-section-label">
        Candidate vessels
        <span>{visible.length}</span>
      </div>

      <div className="inv-cards">
        {visible.map((vessel) => {
          const pct = confidencePct(vessel.attributionConfidence);
          const selected = selectedVesselId === vessel.id;
          const initial = (vessel.name || "V").trim().charAt(0);
          return (
            <button
              key={vessel.id}
              type="button"
              className={`inv-vessel-card ${selected ? "is-selected" : ""}`}
              onClick={() => onSelectVessel?.(vessel)}
            >
              <div className="inv-case-top">
                <strong>#{vessel.mmsi || vessel.id}</strong>
                <span className={`inv-badge ${statusClass(pct)}`}>
                  {pct == null
                    ? "Not scored"
                    : `${pct >= 70 ? "High" : pct >= 40 ? "Medium" : "Low"} · ${pct}%`}
                </span>
              </div>
              <div className="inv-route">
                <span>{vessel.type || "Vessel"}</span>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M3 16h18l-2 4H5l-2-4Z" />
                  <path d="M7 16V9h10v7" />
                </svg>
                <span>Rank {vessel.candidateRank || "—"}</span>
              </div>
              <div className="inv-person">
                <span className="inv-avatar" aria-hidden="true">
                  {initial}
                </span>
                <div>
                  <strong>{vessel.name}</strong>
                  <small>{vessel.flag || "AIS track"}</small>
                </div>
              </div>
            </button>
          );
        })}
        {!visible.length && (
          <p className="inv-empty">
            {pipelineStage >= 1
              ? "Probable source region estimated. Run attribution to scan AIS traffic inside it and rank candidate vessels."
              : "No candidates yet. Run hindcast to trace the slick back to its probable source region."}
          </p>
        )}
      </div>

      {backendHost && (
        <p className="inv-host" title={backendHost}>
          {backendHost.replace(/^https?:\/\//, "")}
        </p>
      )}
    </section>
  );
}
