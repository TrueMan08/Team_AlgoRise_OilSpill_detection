import "./EvidencePanel.css";

function EvidencePanel({
  vessel,
  onClose,
  counterfactualResult = null,
}) {
  if (!vessel) {
    return (
      <aside className="evidence-panel">

        <div className="evidence-header">
          <div>
            <span className="evidence-kicker">
              INVESTIGATION
            </span>

            <h2>Evidence</h2>
          </div>

          <button
            className="evidence-close"
            onClick={onClose}
            type="button"
            aria-label="Close evidence panel"
          >
            ×
          </button>
        </div>

        <div className="evidence-empty">
          <div className="evidence-empty-icon">
            ◎
          </div>

          <h3>
            Select a candidate vessel
          </h3>

          <p>
            Select a vessel on the map to
            inspect the evidence supporting
            its attribution score.
          </p>
        </div>

      </aside>
    );
  }

  // =====================================================
  // SCORING ENGINE RESULT
  // =====================================================

  const scoring =
    vessel.scoring || {};

  const confidence =
    scoring.confidence ??
    Math.round(
      (vessel.attributionConfidence ||
        0) * 100
    );

  const evidenceItems =
    scoring.evidenceItems || [];

  const strongSignals =
    scoring.strongSignals ??
    evidenceItems.filter(
      (item) => item.value >= 80
    ).length;

  const weakSignals =
    scoring.weakSignals ??
    evidenceItems.filter(
      (item) => item.value < 60
    ).length;

  const averageEvidence =
    evidenceItems.length
      ? Math.round(
          evidenceItems.reduce(
            (sum, item) =>
              sum + item.value,
            0
          ) /
            evidenceItems.length
        )
      : 0;

  const assessment =
    scoring.assessment ||
    "Low attribution support";

  const assessmentClass =
    scoring.assessmentClass ||
    "weak";

  // =====================================================
  // SIGNAL STRENGTH
  // =====================================================

  const getStrength = (
    value
  ) => {
    if (value >= 80) {
      return "Strong";
    }

    if (value >= 60) {
      return "Moderate";
    }

    return "Weak";
  };

  const getClass = (
    value
  ) => {
    if (value >= 80) {
      return "strong";
    }

    if (value >= 60) {
      return "moderate";
    }

    return "weak";
  };

  // =====================================================
  // RETURN
  // =====================================================

  return (
    <aside className="evidence-panel">

      {/* =================================================
          HEADER
      ================================================= */}

      <div className="evidence-header">
        <div>
          <span className="evidence-kicker">
            ATTRIBUTION EVIDENCE
          </span>

          <h2>
            Evidence Assessment
          </h2>

          <p className="evidence-header-description">
            Investigation signals supporting
            candidate vessel attribution.
          </p>
        </div>

        <button
          className="evidence-close"
          onClick={onClose}
          type="button"
          aria-label="Close evidence panel"
        >
          ×
        </button>
      </div>

      {/* =================================================
          VESSEL SUMMARY
      ================================================= */}

      <div className="evidence-vessel-card">

        <div className="evidence-vessel-rank">
          #{vessel.candidateRank}
        </div>

        <div className="evidence-vessel-info">
          <span className="evidence-vessel-label">
            CANDIDATE VESSEL
          </span>

          <h3>
            {vessel.name}
          </h3>

          <p>
            {vessel.type}

            <span className="evidence-separator">
              |
            </span>

            {vessel.id}
          </p>
        </div>

        <div
          className={`evidence-confidence ${getClass(
            confidence
          )}`}
        >
          <strong>
            {confidence}%
          </strong>

          <span>
            confidence
          </span>
        </div>

      </div>

      {/* =================================================
          ASSESSMENT
      ================================================= */}

      <div
        className={`evidence-assessment ${assessmentClass}`}
      >

        <div className="assessment-icon">
          {assessmentClass ===
          "strong"
            ? "✓"
            : assessmentClass ===
              "moderate"
            ? "!"
            : "×"}
        </div>

        <div className="assessment-content">
          <span>
            ATTRIBUTION ASSESSMENT
          </span>

          <strong>
            {assessment}
          </strong>

          <p>
            {strongSignals} of{" "}
            {evidenceItems.length}{" "}
            evidence signals are
            strong.
          </p>
        </div>

        <div className="assessment-score">
          <strong>
            {averageEvidence}%
          </strong>

          <span>
            signal avg.
          </span>
        </div>

      </div>

      {/* =================================================
          DISCLAIMER
      ================================================= */}

      <div className="evidence-disclaimer">

        <span className="evidence-info-icon">
          i
        </span>

        <span>
          Attribution reflects
          spatial-temporal and
          counterfactual evidence.
          It is not legal certainty.
        </span>

      </div>

      {/* =================================================
          VESSEL OBSERVATION
      ================================================= */}

      <section className="evidence-section">

        <div className="evidence-section-title">
          <span>
            Vessel Observation
          </span>

          <span className="evidence-count">
            CURRENT
          </span>
        </div>

        <div className="vessel-observation-grid">

          <div className="observation-card">
            <span>
              TYPE
            </span>

            <strong>
              {vessel.type ||
                "Unknown"}
            </strong>
          </div>

          <div className="observation-card">
            <span>
              SPEED
            </span>

            <strong>
              {vessel.speedKnots ??
                "—"}

              <small>
                {" "}
                kn
              </small>
            </strong>
          </div>

          <div className="observation-card">
            <span>
              HEADING
            </span>

            <strong>
              {vessel.heading ??
                "—"}

              <small>
                °
              </small>
            </strong>
          </div>

          <div className="observation-card">
            <span>
              RANK
            </span>

            <strong>
              #{vessel.candidateRank}
            </strong>
          </div>

        </div>

      </section>

      {/* =================================================
          EVIDENCE BREAKDOWN
      ================================================= */}

      <section className="evidence-section">

        <div className="evidence-section-title">

          <span>
            Evidence Breakdown
          </span>

          <span className="evidence-count">
            {evidenceItems.length}{" "}
            signals
          </span>

        </div>

        <div className="evidence-list">

          {evidenceItems.map(
            (item) => {

              const strengthClass =
                getClass(item.value);

              const weightPercent =
                Math.round(
                  (item.weight || 0) *
                    100
                );

              return (
                <div
                  className="evidence-item"
                  key={item.key}
                >

                  {/* =================================
                      ICON
                  ================================== */}

                  <div className="evidence-item-icon">
                    {item.icon}
                  </div>

                  {/* =================================
                      MAIN EVIDENCE CONTENT
                  ================================== */}

                  <div className="evidence-item-content">

                    <div className="evidence-item-top">

                      <div className="evidence-item-heading">

                        <span className="evidence-item-category">
                          {item.short}
                        </span>

                        <h4>
                          {item.title}
                        </h4>

                        <p>
                          {String(item.description || "").replace(/^\[[^\]]+\]\s*/, "")}
                        </p>

                      </div>

                      <div
                        className={`evidence-score ${strengthClass}`}
                      >
                        {item.value}%
                      </div>

                    </div>

                    {/* =================================
                        SCORE BAR
                    ================================== */}

                    <div className="evidence-bar">

                      <div
                        className={`evidence-bar-fill ${strengthClass}`}
                        style={{
                          width: `${item.value}%`,
                        }}
                      />

                    </div>

                    {/* =================================
                        STRENGTH
                    ================================== */}

                    <div className="evidence-item-footer">

                      <span
                        className={`evidence-strength ${strengthClass}`}
                      >
                        {getStrength(
                          item.value
                        )}
                      </span>

                    </div>

                  </div>

                  {/* =================================
                      WEIGHT COLUMN
                  ================================== */}

                  <div className="evidence-weight-column">

                    <span className="evidence-weight-label">
                      Weight
                    </span>

                    <span className="evidence-weight">
                      {weightPercent}%
                    </span>

                  </div>

                </div>
              );
            }
          )}

        </div>

      </section>

      {/* =================================================
          WHY THIS VESSEL
      ================================================= */}

      <section className="evidence-section">

        <div className="evidence-section-title">
          <span>
            Why This Candidate?
          </span>
        </div>

        <div className="reason-list">

          {evidenceItems.some(
            (item) =>
              item.key ===
                "spatial" &&
              item.value >= 60
          ) && (
            <div className="reason-item">

              <span className="reason-icon positive">
                ✓
              </span>

              <span>
                Vessel position shows
                meaningful spatial
                compatibility with the
                inferred source region.
              </span>

            </div>
          )}

          {evidenceItems.some(
            (item) =>
              item.key ===
                "temporal" &&
              item.value >= 60
          ) && (
            <div className="reason-item">

              <span className="reason-icon positive">
                ✓
              </span>

              <span>
                Vessel movement overlaps
                the estimated release
                window.
              </span>

            </div>
          )}

          {evidenceItems.some(
            (item) =>
              item.key ===
                "trajectory" &&
              item.value >= 60
          ) && (
            <div className="reason-item">

              <span className="reason-icon positive">
                ✓
              </span>

              <span>
                Observed trajectory is
                compatible with the
                investigation hypothesis.
              </span>

            </div>
          )}

          {evidenceItems.some(
            (item) =>
              item.key ===
                "drift" &&
              item.value >= 60
          ) && (
            <div className="reason-item">

              <span className="reason-icon positive">
                ✓
              </span>

              <span>
                Counterfactual drift
                evidence provides
                supporting movement
                consistency.
              </span>

            </div>
          )}

          {evidenceItems.some(
            (item) =>
              item.key ===
                "aisReliability" &&
              item.value < 80
          ) && (
            <div className="reason-item">

              <span className="reason-icon warning">
                !
              </span>

              <span>
                AIS data contains a
                reliability warning that
                should be considered
                during attribution.
              </span>

            </div>
          )}

          {weakSignals > 0 && (
            <div className="reason-item">

              <span className="reason-icon warning">
                !
              </span>

              <span>
                {weakSignals} evidence
                signal
                {weakSignals > 1
                  ? "s"
                  : ""}{" "}
                remain weak and require
                further validation.
              </span>

            </div>
          )}

        </div>

      </section>

      {/* =================================================
          INVESTIGATION STATUS
      ================================================= */}

      <section className="evidence-section">

        <div className="evidence-section-title">
          Investigation Status
        </div>

        <div className="investigation-status">

          <div className="status-row">

            <span>
              Candidate ranking
            </span>

            <strong>
              #{vessel.candidateRank}
            </strong>

          </div>

          <div className="status-row">

            <span>
              Evidence signals
            </span>

            <strong>
              {strongSignals}/
              {evidenceItems.length}{" "}
              strong
            </strong>

          </div>

          <div className="status-row">

            <span>
              Attribution confidence
            </span>

            <strong
              className={getClass(
                confidence
              )}
            >
              {confidence}%
            </strong>

          </div>

          <div className="status-row">

            <span>
              Investigation state
            </span>

            <strong
              className={`status-pill ${assessmentClass}`}
            >
              {assessmentClass ===
              "strong"
                ? "SUPPORTED"
                : assessmentClass ===
                  "moderate"
                ? "REVIEW"
                : "WEAK"}
            </strong>

          </div>

        </div>

      </section>

      {/* =================================================
          COUNTERFACTUAL PHYSICAL VALIDATION (STEP 6)
      ================================================= */}
      <section className="evidence-section" style={{ borderTop: "1px solid rgba(148, 163, 184, 0.15)", paddingTop: "14px" }}>
        <div className="evidence-section-header">
          <div>
            <span className="section-kicker">STEP 6 VALIDATION</span>
            <h3>Counterfactual Drift Plausibility</h3>
          </div>
          <span
            style={{
              fontSize: "11px",
              padding: "2px 8px",
              borderRadius: "4px",
              fontWeight: 700,
              backgroundColor: "rgba(34, 197, 94, 0.15)",
              color: "#4ade80",
              border: "1px solid rgba(34, 197, 94, 0.3)",
            }}
          >
            {counterfactualResult?.evidence_strength ? `${counterfactualResult.evidence_strength} Evidence` : "Not yet validated"}
          </span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginTop: "10px" }}>
          <div style={{ padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
            <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Spatial Agreement</span>
            <div style={{ fontSize: "14px", fontWeight: 800, color: "#0284c7", marginTop: "3px", fontFamily: "monospace" }}>
              {counterfactualResult?.spatial_agreement != null
                ? `${Math.round(counterfactualResult.spatial_agreement * 100)}% IoU`
                : "—"}
            </div>
          </div>

          <div style={{ padding: "10px 12px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(15, 23, 42, 0.04)" }}>
            <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Trajectory Reaches Slick</span>
            <div style={{ fontSize: "12px", fontWeight: 800, color: counterfactualResult == null ? "#64748b" : counterfactualResult.trajectory_reaches_slick ? "#16a34a" : "#dc2626", marginTop: "3px" }}>
              {counterfactualResult == null
                ? "—"
                : counterfactualResult.trajectory_reaches_slick
                  ? "TRUE (Intersection)"
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
            <span style={{ fontSize: "10px", textTransform: "uppercase", color: "#64748b", fontWeight: 700, letterSpacing: "0.04em", display: "block" }}>Validation Engine</span>
            <div style={{ fontSize: "12px", fontWeight: 700, color: "#334155", marginTop: "3px" }}>
              OpenOil / CMEMS
            </div>
          </div>
        </div>

        <div
          style={{
            marginTop: "10px",
            padding: "10px 12px",
            backgroundColor: "#f8fafc",
            borderRadius: "6px",
            border: "1px solid #cbd5e1",
            borderLeft: "3px solid #0284c7",
            fontFamily: "monospace",
            fontSize: "11px",
            lineHeight: 1.55,
            color: "#0f172a",
          }}
        >
          {counterfactualResult?.explanation ||
            "Counterfactual validation has not run yet. Run hindcast to simulate this vessel's forward drift against the observed slick."}
        </div>
      </section>

      {/* =================================================
          METHODOLOGY
      ================================================= */}

      <div className="evidence-method">

        <div className="method-title">
          Attribution Method
        </div>

        <p>
          Candidate confidence is
          calculated from weighted
          spatial, temporal, trajectory,
          counterfactual drift and AIS
          reliability signals.
        </p>

        <div className="method-flow">

          <span>
            Spatial
          </span>

          <span>+</span>

          <span>
            Temporal
          </span>

          <span>+</span>

          <span>
            Trajectory
          </span>

          <span>+</span>

          <span>
            Drift
          </span>

          <span>+</span>

          <span>
            AIS
          </span>

        </div>

      </div>

    </aside>
  );
}

export default EvidencePanel;