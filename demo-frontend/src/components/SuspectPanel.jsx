import { useState, useMemo } from "react";
import "./SuspectPanel.css";

export function SuspectPanel({
  selectedVessel,
  allVessels = [],
  onSelectVessel,
  onClose,
  counterfactualResult = null,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [riskFilter, setRiskFilter] = useState("all");
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const getAisStatusClass = (status) => {
    const value = (status || "").toLowerCase();

    if (
      value === "good" ||
      value === "optimal" ||
      value === "nominal"
    ) {
      return "badge-good";
    }

    if (
      value === "warning" ||
      value === "degraded"
    ) {
      return "badge-warning";
    }

    if (
      value === "critical" ||
      value === "bad"
    ) {
      return "badge-danger";
    }

    return "badge-neutral";
  };

  const getScoreColor = (score) => {
    if (score >= 0.7) return "#3b82f6";
    if (score >= 0.5) return "#2563eb";

    return "#64748b";
  };

  const topCandidate = useMemo(() => {
    if (!allVessels || !allVessels.length) {
      return null;
    }

    return (
      allVessels.find(
        (v) => v.candidateRank === 1
      ) || allVessels[0]
    );
  }, [allVessels]);

  const filteredVessels = useMemo(() => {
    if (!Array.isArray(allVessels)) {
      return [];
    }

    return allVessels.filter((vessel) => {
      const name = (
        vessel.name || ""
      ).toLowerCase();

      const type = (
        vessel.type || ""
      ).toLowerCase();

      const id = (
        vessel.id || ""
      ).toLowerCase();

      const flag = (
        vessel.flag || ""
      ).toLowerCase();

      const query = searchQuery
        .toLowerCase()
        .trim();

      const matchesSearch =
        !query ||
        name.includes(query) ||
        type.includes(query) ||
        id.includes(query) ||
        flag.includes(query);

      const conf =
        Number(
          vessel.attributionConfidence
        ) || 0;

      let matchesFilter = true;

      if (riskFilter === "high") {
        matchesFilter = conf >= 0.6;
      } else if (riskFilter === "medium") {
        matchesFilter =
          conf >= 0.4 && conf < 0.6;
      } else if (riskFilter === "low") {
        matchesFilter = conf < 0.4;
      }

      return matchesSearch && matchesFilter;
    });
  }, [
    allVessels,
    searchQuery,
    riskFilter,
  ]);

  const currentIndex = selectedVessel
    ? allVessels.findIndex(
        (v) => v.id === selectedVessel.id
      )
    : -1;

  const handlePrev = () => {
    if (currentIndex > 0) {
      onSelectVessel(
        allVessels[currentIndex - 1]
      );
    } else if (allVessels.length > 0) {
      onSelectVessel(
        allVessels[allVessels.length - 1]
      );
    }
  };

  const handleNext = () => {
    if (
      currentIndex >= 0 &&
      currentIndex < allVessels.length - 1
    ) {
      onSelectVessel(
        allVessels[currentIndex + 1]
      );
    } else if (allVessels.length > 0) {
      onSelectVessel(allVessels[0]);
    }
  };

  /*
   * =====================================================
   * OVERVIEW STATE
   * =====================================================
   */

  if (!selectedVessel) {
    return (
      <aside
        className="suspect-panel suspect-panel-open"
        aria-label="Vessel investigation"
      >
        {/* HEADER */}
        <div className="panel-header">
          <div>
            <div className="panel-kicker-row">
              <span className="panel-kicker">
                MARITIME SURVEILLANCE &amp;
                ATTRIBUTION
              </span>
            </div>

            <h2>
              Vessel Investigation
            </h2>

            <p className="panel-header-description">
              Candidate vessels evaluated against
              backtracked Lagrangian source region.
            </p>
          </div>

          <button
            type="button"
            className="close-button"
            onClick={onClose}
            aria-label="Close vessel investigation"
          >
            ×
          </button>
        </div>

        <div className="panel-scroll-content">
          {/* QUICK METRICS */}
          <div className="investigation-metrics-grid">
            <div className="investigation-metric-card">
              <span className="metric-label">
                TRACKED TARGETS
              </span>

              <span className="metric-val">
                {allVessels.length}
              </span>

              <span className="metric-sub">
                in corridor
              </span>
            </div>

            <div className="investigation-metric-card highlight-metric">
              <span className="metric-label">
                TOP MATCH
              </span>

              <span className="metric-val">
                {topCandidate
                  ? Math.round(
                      (topCandidate.attributionConfidence ||
                        0) * 100
                    )
                  : 0}
                %
              </span>

              <span className="metric-sub">
                {topCandidate?.name ||
                  "None"}
              </span>
            </div>

            <div className="investigation-metric-card">
              <span className="metric-label">
                EST. RELEASE
              </span>

              <span className="metric-val">
                {topCandidate?.releaseTime
                  ? new Date(topCandidate.releaseTime)
                      .toISOString()
                      .substring(11, 16)
                  : "—"}
              </span>

              <span className="metric-sub">
                {topCandidate?.releaseTime ? "UTC · from attribution" : "pending forward run"}
              </span>
            </div>
          </div>

          {/* PRIMARY SUSPECT */}
          {topCandidate &&
            !searchQuery &&
            riskFilter === "all" && (
              <div className="primary-suspect-spotlight">
                <div className="spotlight-badge">
                  <span className="spotlight-star">
                    ★
                  </span>

                  <span>
                    TOP CANDIDATE VESSEL
                  </span>
                </div>

                <div className="spotlight-body">
                  <div className="spotlight-title-row">
                    <div>
                      <h3 className="spotlight-name">
                        {topCandidate.name}
                      </h3>

                      <span className="spotlight-type">
                        {topCandidate.type ||
                          "Vessel"}{" "}
                        •{" "}
                        {topCandidate.flag ||
                          "—"}
                      </span>
                    </div>

                    <div className="spotlight-score-pill">
                      <span className="score-num">
                        {Math.round(
                          (topCandidate.attributionConfidence ||
                            0) * 100
                        )}
                        %
                      </span>

                      <span className="score-lbl">
                        MATCH
                      </span>
                    </div>
                  </div>

                  <div className="spotlight-meter">
                    <div
                      className="spotlight-meter-fill"
                      style={{
                        width: `${Math.round(
                          (topCandidate.attributionConfidence ||
                            0) * 100
                        )}%`,
                      }}
                    />
                  </div>

                  <div className="spotlight-tags">
                    <span className="spotlight-tag alert-tag">
                      Trajectory Crossing
                    </span>

                    <span className="spotlight-tag warn-tag">
                      Speed Anomaly (
                      {topCandidate.speedKnots ??
                        "N/A"}{" "}
                      kts)
                    </span>

                    <span className="spotlight-tag">
                      Heading{" "}
                      {topCandidate.heading ??
                        0}
                      °
                    </span>
                  </div>

                  <button
                    type="button"
                    className="spotlight-action-btn"
                    onClick={() =>
                      onSelectVessel(
                        topCandidate
                      )
                    }
                  >
                    <span>
                      Inspect Forensic Evidence
                    </span>

                    <span className="btn-arrow">
                      →
                    </span>
                  </button>
                </div>
              </div>
            )}

          {/* ALL CANDIDATES */}
          <div className="candidate-overview-section">
            <div className="section-title-row">
              <span className="overview-label">
                ALL CANDIDATE VESSELS
              </span>

              <span className="candidate-count-badge">
                {filteredVessels.length} of{" "}
                {allVessels.length} Available
              </span>
            </div>

            {/* SEARCH */}
            <div className="vessel-search-bar-wrap">
              <span
                className="search-icon"
                aria-hidden="true"
              >
                <svg
                  viewBox="0 0 24 24"
                  width="16"
                  height="16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle
                    cx="11"
                    cy="11"
                    r="7"
                  />

                  <path d="m20 20-4-4" />
                </svg>
              </span>

              <input
                type="text"
                className="vessel-search-input"
                placeholder="Search by vessel name, MMSI, type..."
                value={searchQuery}
                onChange={(e) =>
                  setSearchQuery(
                    e.target.value
                  )
                }
                aria-label="Search vessels"
              />

              {searchQuery && (
                <button
                  type="button"
                  className="clear-search-btn"
                  onClick={() =>
                    setSearchQuery("")
                  }
                  aria-label="Clear search"
                >
                  ×
                </button>
              )}
            </div>

            {/* FILTERS */}
            <div className="risk-filter-chips">
              <button
                type="button"
                className={`filter-chip ${
                  riskFilter === "all"
                    ? "filter-chip-active"
                    : ""
                }`}
                onClick={() =>
                  setRiskFilter("all")
                }
              >
                All ({allVessels.length})
              </button>

              <button
                type="button"
                className={`filter-chip filter-high ${
                  riskFilter === "high"
                    ? "filter-chip-active"
                    : ""
                }`}
                onClick={() =>
                  setRiskFilter("high")
                }
              >
                High Risk (≥60%)
              </button>

              <button
                type="button"
                className={`filter-chip filter-med ${
                  riskFilter === "medium"
                    ? "filter-chip-active"
                    : ""
                }`}
                onClick={() =>
                  setRiskFilter("medium")
                }
              >
                Medium (40-59%)
              </button>

              <button
                type="button"
                className={`filter-chip filter-low ${
                  riskFilter === "low"
                    ? "filter-chip-active"
                    : ""
                }`}
                onClick={() =>
                  setRiskFilter("low")
                }
              >
                Low (&lt;40%)
              </button>
            </div>

            {/* CANDIDATE CARDS */}
            <div className="candidate-card-list">
              {filteredVessels.length === 0 ? (
                <div className="no-vessels-found">
                  <span>
                    No vessels match the search
                    criteria.
                  </span>

                  <button
                    type="button"
                    className="reset-filter-btn"
                    onClick={() => {
                      setSearchQuery("");
                      setRiskFilter("all");
                    }}
                  >
                    Reset Filters
                  </button>
                </div>
              ) : (
                filteredVessels.map(
                  (vessel) => {
                    const confPercent =
                      Math.round(
                        (vessel.attributionConfidence ||
                          0) * 100
                      );

                    const isTop =
                      vessel.candidateRank ===
                      1;

                    return (
                      <button
                        key={vessel.id}
                        type="button"
                        className={`candidate-entry-card ${
                          isTop
                            ? "candidate-card-top"
                            : ""
                        }`}
                        onClick={() =>
                          onSelectVessel(
                            vessel
                          )
                        }
                      >
                        <div className="card-main-info">
                          <div className="card-name-row">
                            <span className="vessel-title">
                              {vessel.name ||
                                "Unknown Vessel"}
                            </span>

                            <span
                              className={`vessel-conf-badge conf-${
                                confPercent >=
                                60
                                  ? "high"
                                  : confPercent >=
                                    40
                                  ? "med"
                                  : "low"
                              }`}
                            >
                              {confPercent}%
                            </span>
                          </div>

                          <div className="card-sub-row">
                            <span>
                              {vessel.type ||
                                "Vessel"}
                            </span>

                            <span>•</span>

                            <span>
                              {vessel.speedKnots ??
                                "N/A"}{" "}
                              kts
                            </span>

                            <span>•</span>

                            <span>
                              {vessel.heading ??
                                0}
                              °
                            </span>
                          </div>

                          <div className="candidate-mini-bar">
                            <div
                              className="candidate-mini-fill"
                              style={{
                                width: `${confPercent}%`,
                                backgroundColor: "#2563eb",
                              }}
                            />
                          </div>
                        </div>

                        <div className="card-chevron">
                          ›
                        </div>
                      </button>
                    );
                  }
                )
              )}
            </div>
          </div>
        </div>
      </aside>
    );
  }

  /*
   * =====================================================
   * SELECTED CANDIDATE VIEW
   * =====================================================
   */

  const {
    candidateRank,
    name,
    type,
    speedKnots,
    heading,
    attributionConfidence,
    minDistanceKm,
    releaseLocation,
    releaseTime,
    observationTime,
    explanation,
    aisGaps,
    evidence,
  } = selectedVessel;

  const confidencePercent = Math.round(
    (attributionConfidence || 0) * 100
  );

  return (
    <aside
      className="suspect-panel suspect-panel-open"
      aria-label="Vessel investigation"
    >
      {/* HEADER */}
      <div className="panel-header">
        <div>
          <span className="panel-kicker">
            VESSEL FORENSIC DOSSIER
          </span>

          <h2>
            {name || "Candidate Vessel"}
          </h2>

          <p className="panel-header-description">
            Analytical attribution evidence and
            trajectory match.
          </p>
        </div>

        <button
          type="button"
          className="close-button"
          onClick={onClose}
          aria-label="Close vessel investigation"
        >
          ×
        </button>
      </div>

      {/* VESSEL SWITCHER */}
      <div className="vessel-selector-stepper-bar">
        <button
          type="button"
          className="stepper-nav-btn"
          onClick={handlePrev}
          title="Previous candidate"
          aria-label="Previous candidate"
        >
          ◀
        </button>

        <div className="stepper-dropdown-container">
          <button
            type="button"
            className="stepper-current-trigger"
            onClick={() =>
              setDropdownOpen(
                (prev) => !prev
              )
            }
          >
            <span
              className={`stepper-rank-tag rank-${
                candidateRank || "other"
              }`}
            >
              #{candidateRank || "-"}
            </span>

            <span className="stepper-name-text">
              {name}
            </span>

            <span className="stepper-conf-text">
              {confidencePercent}%
            </span>

            <span className="stepper-arrow">
              {dropdownOpen ? "▲" : "▼"}
            </span>
          </button>

          {dropdownOpen && (
            <div className="stepper-dropdown-menu">
              <div className="dropdown-header-row">
                <span>
                  SELECT TARGET (
                  {allVessels.length})
                </span>
              </div>

              <div className="dropdown-items-scroll">
                {allVessels.map((v) => {
                  const isCur =
                    v.id === selectedVessel.id;

                  const cPct = Math.round(
                    (v.attributionConfidence ||
                      0) * 100
                  );

                  return (
                    <button
                      key={v.id}
                      type="button"
                      className={`dropdown-item-btn ${
                        isCur
                          ? "dropdown-item-active"
                          : ""
                      }`}
                      onClick={() => {
                        onSelectVessel(v);
                        setDropdownOpen(false);
                      }}
                    >
                      <span className="item-rank">
                        #{v.candidateRank}
                      </span>

                      <span className="item-name">
                        {v.name}
                      </span>

                      <span className="item-type">
                        {v.type || "Vessel"}
                      </span>

                      <span className="item-conf">
                        {cPct}%
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <button
          type="button"
          className="stepper-nav-btn"
          onClick={handleNext}
          title="Next candidate"
          aria-label="Next candidate"
        >
          ▶
        </button>
      </div>

      <div className="panel-scroll-content">
        {/* IDENTITY */}
        <section className="panel-section identity-section">
          <div className="identity-heading">
            <div
              className={`identity-marker rank-${
                candidateRank || "other"
              }`}
            >
              <span>▲</span>
            </div>

            <div>
              <span className="section-label">
                {candidateRank === 1
                  ? "★ TOP CANDIDATE"
                  : `CANDIDATE RANK #${
                      candidateRank || "-"
                    }`}
              </span>

              <h2 className="vessel-name">
                {name}
              </h2>

              <div className="vessel-type-badge">
                {type || "Commercial"} Vessel

                {selectedVessel.flag && (
                  <span className="vessel-flag">
                    {" "}
                    • {selectedVessel.flag}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="vessel-telemetry-grid">
            <div className="telemetry-item">
              <span className="telemetry-label">
                Speed
              </span>

              <span className="telemetry-value">
                {speedKnots ?? "N/A"} kts
              </span>
            </div>

            <div className="telemetry-item">
              <span className="telemetry-label">
                Heading
              </span>

              <span className="telemetry-value">
                {heading ?? 0}°
              </span>
            </div>

            <div className="telemetry-item">
              <span className="telemetry-label">
                Candidate Rank
              </span>

              <span className="telemetry-value">
                #{candidateRank || "-"} of{" "}
                {allVessels.length}
              </span>
            </div>

            <div className="telemetry-item">
              <span className="telemetry-label">
                Vessel ID
              </span>

              <span className="telemetry-value mono">
                {selectedVessel.id}
              </span>
            </div>
          </div>
        </section>

        {/* CONFIDENCE */}
        <section className="panel-section confidence-section">
          <div className="confidence-header">
            <div className="confidence-title-group">
              <span className="section-label">
                ATTRIBUTION SCORE
              </span>

              <h3 className="confidence-heading">
                Attribution Confidence
              </h3>
            </div>

            <div
              className={`confidence-value-pill conf-${
                confidencePercent >= 60
                  ? "high"
                  : confidencePercent >= 40
                  ? "med"
                  : "low"
              }`}
            >
              {confidencePercent}%
            </div>
          </div>

          <div className="confidence-meter-container">
            <div
              className="confidence-meter-bar"
              style={{
                width: `${confidencePercent}%`,
                backgroundColor: "#2563eb",
              }}
            />
          </div>

          <p className="confidence-disclaimer">
            <span
              className="info-icon"
              aria-hidden="true"
            >
              i
            </span>

            <span>
              Attribution score reflects
              spatial-temporal and
              counterfactual evidence, not legal
              certainty.
            </span>
          </p>
        </section>

        {/* EVIDENCE */}
        <section className="panel-section evidence-section">
          <div className="section-heading-row">
            <h3 className="section-title">
              Evidence Breakdown
            </h3>

            <span className="section-count">
              5 signals
            </span>
          </div>

          <div className="evidence-cards-list">
            {[
              [
                "Spatial Proximity",
                evidence?.spatial,
              ],
              [
                "Temporal Window",
                evidence?.temporal,
              ],
              [
                "Trajectory Compatibility",
                evidence?.trajectory,
              ],
              [
                "Drift & Counterfactual",
                evidence?.drift,
              ],
            ].map(
              ([title, item]) =>
                item && (
                  <div
                    className="evidence-card"
                    key={title}
                  >
                    <div className="evidence-card-header">
                      <div className="evidence-label-group">
                        <span className="evidence-category">
                          {title}
                        </span>

                        <span className="evidence-desc">
                          {String(item.label || "").replace(/^\[[^\]]+\]\s*/, "")}
                        </span>
                      </div>

                      <span className="evidence-score-badge">
                        {Math.round(
                          (item.score || 0) *
                            100
                        )}
                        %
                      </span>
                    </div>

                    <div className="evidence-bar-bg">
                      <div
                        className="evidence-bar-fill"
                        style={{
                          width: `${Math.round(
                            (item.score || 0) *
                              100
                          )}%`,
                          backgroundColor:
                            getScoreColor(
                              item.score || 0
                            ),
                        }}
                      />
                    </div>
                  </div>
                )
            )}

            {evidence?.aisReliability && (
              <div className="evidence-card ais-card">
                <div className="evidence-card-header">
                  <div className="evidence-label-group">
                    <span className="evidence-category">
                      AIS Reliability
                    </span>

                    <span className="evidence-desc">
                      {String(evidence.aisReliability.label || "").replace(/^\[[^\]]+\]\s*/, "")}
                    </span>
                  </div>

                  <span
                    className={`ais-status-badge ${getAisStatusClass(
                      evidence.aisReliability
                        .status
                    )}`}
                  >
                    {
                      evidence.aisReliability
                        .status
                    }
                  </span>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ESTIMATED RELEASE STATE (BACKEND ATTRIBUTION CONTRACT) */}
        <section className="panel-section" style={{ borderTop: "1px solid rgba(148, 163, 184, 0.15)", paddingTop: "14px" }}>
          <div className="section-heading-row">
            <h3 className="section-title">Estimated Release State</h3>
            <span className="section-count mono">#{candidateRank || 1}</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginTop: "10px" }}>
            <div style={{ padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
              <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Release Location</span>
              <div style={{ fontSize: "12px", fontFamily: "monospace", fontWeight: 700, color: "#0f172a", marginTop: "3px" }}>
                {Number.isFinite(Number(releaseLocation?.lat)) && Number.isFinite(Number(releaseLocation?.lon))
                  ? `${Number(releaseLocation.lat).toFixed(4)}°N, ${Number(releaseLocation.lon).toFixed(4)}°E`
                  : "—"}
              </div>
            </div>

            <div style={{ padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
              <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Min Distance</span>
              <div style={{ fontSize: "12px", fontFamily: "monospace", fontWeight: 700, color: "#0f172a", marginTop: "3px" }}>
                {minDistanceKm != null ? `${Number(minDistanceKm).toFixed(1)} km to polygon` : "—"}
              </div>
            </div>

            <div style={{ padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
              <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Release Time</span>
              <div style={{ fontSize: "12px", fontFamily: "monospace", fontWeight: 700, color: "#0369a1", marginTop: "3px" }}>
                {releaseTime ? new Date(releaseTime).toISOString().replace("T", " ").substring(0, 16) + " UTC" : "—"}
              </div>
            </div>

            <div style={{ padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
              <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Observation Time</span>
              <div style={{ fontSize: "12px", fontFamily: "monospace", fontWeight: 700, color: "#0369a1", marginTop: "3px" }}>
                {observationTime ? new Date(observationTime).toISOString().replace("T", " ").substring(0, 16) + " UTC" : "—"}
              </div>
            </div>
          </div>

          <div style={{ marginTop: "8px", padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
            <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>AIS Data Continuity</span>
            <div style={{ fontSize: "12px", fontWeight: 600, color: "#1e293b", marginTop: "3px" }}>
              {aisGaps && aisGaps.length > 0
                ? `${aisGaps.length} observation gap(s) detected (>30 min)`
                : "Continuous AIS tracking (0 reporting gaps detected)"}
            </div>
          </div>
        </section>

        {/* BACKEND EXPLANATION (MONOSPACE) */}
        <section className="panel-section" style={{ borderTop: "1px solid rgba(148, 163, 184, 0.15)", paddingTop: "14px" }}>
          <div className="section-heading-row">
            <h3 className="section-title">Backend Forensic Summary</h3>
            <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#1d4ed8", fontWeight: 700, backgroundColor: "#eff6ff", padding: "2px 6px", borderRadius: "4px", border: "1px solid rgba(37, 99, 235, 0.25)" }}>API Justification</span>
          </div>

          <div
            style={{
              marginTop: "8px",
              padding: "10px 12px",
              backgroundColor: "#f8fafc",
              border: "1px solid #cbd5e1",
              borderLeft: "3px solid #2563eb",
              borderRadius: "6px",
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
              fontSize: "11px",
              lineHeight: 1.55,
              color: "#0f172a",
              fontWeight: 500,
            }}
          >
            {explanation ||
              "No backend justification for this vessel yet — run attribution to score it against the source region."}
          </div>
        </section>

        {/* COUNTERFACTUAL PHYSICAL VALIDATION — this panel owns the full
            reasoning for the SELECTED candidate; the case queue carries only
            the compact cross-candidate comparison. */}
        <section className="panel-section" style={{ borderTop: "1px solid rgba(148, 163, 184, 0.15)", paddingTop: "14px", marginBottom: "16px" }}>
          <p style={{ margin: "0 0 10px", fontSize: "11.5px", lineHeight: 1.5, color: "#475569" }}>
            If oil had been released from{" "}
            <strong style={{ color: "#0f172a" }}>{name || selectedVessel.mmsi}</strong> at its
            estimated release state
            {releaseTime
              ? ` (${new Date(releaseTime).toISOString().replace("T", " ").substring(0, 16)} UTC`
              : ""}
            {releaseLocation
              ? `, ${Number(releaseLocation.lat).toFixed(4)}°N ${Number(releaseLocation.lon).toFixed(4)}°E)`
              : releaseTime
                ? ")"
                : ""}
            , the backend drift model predicts the following against the
            observed SAR slick.
          </p>
          <div className="section-heading-row">
            <h3 className="section-title">Counterfactual Plausibility</h3>
            <span
              style={{
                fontSize: "10px",
                padding: "2px 6px",
                borderRadius: "4px",
                fontWeight: 700,
                backgroundColor: "#eff6ff",
                color: "#1d4ed8",
                border: "1px solid rgba(37, 99, 235, 0.25)",
              }}
            >
              {counterfactualResult?.evidence_strength ? `${counterfactualResult.evidence_strength} Evidence` : "Not yet validated"}
            </span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginTop: "10px" }}>
            <div style={{ padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
              <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Spatial Agreement</span>
              <div style={{ fontSize: "14px", fontWeight: 800, color: "#1d4ed8", marginTop: "3px", fontFamily: "monospace" }}>
                {counterfactualResult?.spatial_agreement != null
                  ? `${Math.round(counterfactualResult.spatial_agreement * 100)}% Jaccard`
                  : "—"}
              </div>
            </div>

            <div style={{ padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
              <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Trajectory Intersection</span>
              <div style={{ fontSize: "12px", fontWeight: 800, color: "#1d4ed8", marginTop: "3px" }}>
                {counterfactualResult == null
                  ? "—"
                  : counterfactualResult.trajectory_reaches_slick
                    ? "TRUE (Reaches Slick)"
                    : "FALSE (Diverged)"}
              </div>
            </div>

            <div style={{ padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
              <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Centroid Offset</span>
              <div style={{ fontSize: "14px", fontWeight: 800, color: "#0f172a", marginTop: "3px", fontFamily: "monospace" }}>
                {counterfactualResult?.centroid_distance_km != null
                  ? `${counterfactualResult.centroid_distance_km.toFixed(2)} km`
                  : "—"}
              </div>
            </div>

            <div style={{ padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
              <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Simulation Model</span>
              <div style={{ fontSize: "12px", fontWeight: 700, color: "#334155", marginTop: "3px" }}>
                OpenOil Lagrangian
              </div>
            </div>
          </div>

          <p style={{ fontSize: "11.5px", color: "#475569", lineHeight: 1.45, marginTop: "10px", fontStyle: "italic" }}>
            {counterfactualResult?.explanation ||
              "Counterfactual validation has not run yet. Run hindcast to simulate this vessel's forward drift against the observed slick."}
          </p>
        </section>
      </div>

      {/* FOOTER */}
      <div className="panel-footer">
        <button
          type="button"
          className="deselect-action-btn"
          onClick={onClose}
        >
          ← Back to All Candidates
        </button>
      </div>
    </aside>
  );
}

export default SuspectPanel;