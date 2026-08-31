import { fmtUtc } from "../geo.js";

const Info = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
    <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.4" />
    <path d="M8 7v4M8 4.6v.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);

function Bar({ name, score }) {
  return (
    <div className="ebar">
      <div className="top"><span className="n">{name}</span><span className="s">{score.toFixed(1)}</span></div>
      <div className="rail"><div className="fill" style={{ width: `${Math.min(100, score)}%` }} /></div>
    </div>
  );
}

function ConfChip({ conf }) {
  const c = (conf || "").toLowerCase();
  const cls = c.startsWith("high") ? "conf-high" : c.startsWith("med") || c.startsWith("mod") ? "conf-med" : "conf-low";
  return <div className={`conf-chip ${cls}`}>{(conf || "—").toUpperCase()}<br /><span style={{ fontWeight: 500, fontSize: 10 }}>Confidence</span></div>;
}

function StageButton({ label, running, disabled, onClick, ghost }) {
  return (
    <button className={`btn ${ghost ? "btn-ghost" : "btn-primary"}`} disabled={disabled || running} onClick={onClick}>
      {running ? <><span className="spinner" style={{ borderTopColor: "#fff" }} /> {label.replace(/^Run |^Find |^Rank |^Compare/, "Running")}…</> : <>▶ {label}</>}
    </button>
  );
}

export default function RightPanel({ inv, status, errors, actions, selectedMmsi, onSelectVessel, selectedCandidate, backend, lookback, onLookback }) {
  const err = (id) => errors[id] && <div className="err-box">{errors[id]}
    {backend !== "online" && <div style={{ marginTop: 5 }}>Backend is starting — this may take a moment. Retry shortly.</div>}</div>;

  // ---------- nothing yet ----------
  if (!inv.slick)
    return (
      <aside className="rightpanel">
        <div className="panel-h">DETECTION</div>
        <div className="pcard tint">
          <h3>No observed slick yet</h3>
          <p style={{ fontSize: 12.5, color: "var(--mut)", lineHeight: 1.5 }}>
            Load the Norway demo scenario to start from a detected slick, or
            connect a detection source. All downstream analysis is computed by
            the OilTrace backend.
          </p>
          <StageButton label="Load Norway Demo Detection" onClick={actions.loadDemo} />
        </div>
      </aside>
    );

  const cf = inv.counterfactual;
  const att = inv.attribution;
  const vesselByMmsi = Object.fromEntries((inv.vessels || []).map((v) => [v.mmsi, v]));

  return (
    <aside className="rightpanel">
      {/* ---------- observed slick ---------- */}
      <div className="panel-h">OBSERVED SLICK</div>
      <div className="pcard">
        <div className="kv"><span className="k">Slick ID</span><span className="v" style={{ fontFamily: "var(--mono)", fontSize: 11.5 }}>{inv.slick.id}</span></div>
        <div className="kv"><span className="k">Detection time</span><span className="v">{fmtUtc(inv.slick.timestamp_utc)}</span></div>
        <div className="kv"><span className="k">Centroid</span><span className="v">{inv.slick.centroid.lat.toFixed(3)}°N, {inv.slick.centroid.lon.toFixed(3)}°E</span></div>
        <div className="kv"><span className="k">Area</span><span className="v">{inv.slick.area_km2.toFixed(1)} km²</span></div>
        <div className="kv"><span className="k">Detection confidence</span><span className="v">{inv.slick.confidence.toFixed(2)}</span></div>
        {status.hindcast !== "done" && (
          <>
            <div className="kv" style={{ alignItems: "center" }}>
              <span className="k">Hindcast lookback</span>
              <select value={lookback} onChange={(e) => onLookback(Number(e.target.value))}
                style={{ border: "1px solid var(--line)", borderRadius: 7, padding: "4px 8px", fontFamily: "var(--sans)", fontSize: 12 }}>
                <option value={2}>2 hours</option><option value={6}>6 hours</option>
                <option value={12}>12 hours</option><option value={24}>24 hours</option>
              </select>
            </div>
            <StageButton label="Run Backward Simulation" running={status.hindcast === "running"} onClick={actions.runHindcast} disabled={backend === "offline"} />
          </>
        )}
        {err("hindcast")}
      </div>

      {/* ---------- hindcast ---------- */}
      {inv.hindcast && (
        <>
          <div className="panel-h">PROBABLE SOURCE REGION</div>
          <div className="pcard">
            {inv.hindcast.source_region.candidate_regions.map((c, i) => (
              <div key={c.id} style={{ marginBottom: 6 }}>
                <div className="kv"><span className="k">Candidate {i + 1} window</span>
                  <span className="v" style={{ fontSize: 11.5 }}>{fmtUtc(c.start_time_utc)} → {fmtUtc(c.end_time_utc)}</span></div>
                <div className="kv"><span className="k">Source-region probability mass</span>
                  <span className="v">{(c.probability * 100).toFixed(0)}%</span></div>
              </div>
            ))}
            <div className="notice"><Info />Probability mass of the reconstructed source density — not a probability that any vessel caused the spill.</div>
            {status.vessels !== "done" && (
              <StageButton label="Find Vessels" running={status.vessels === "running"} onClick={actions.findVessels} disabled={status.hindcast !== "done"} />
            )}
            {err("vessels")}
          </div>
        </>
      )}

      {/* ---------- vessels ---------- */}
      {inv.vessels && (
        <>
          <div className="panel-h">AIS VESSELS · {inv.vessels.length} FOUND {inv.demo && "· SYNTHETIC DATA"}</div>
          <div className="pcard" style={{ padding: 8 }}>
            <table className="cand-table">
              <thead><tr><th>VESSEL</th><th>TYPE</th><th>AIS PTS</th><th>GAPS</th></tr></thead>
              <tbody>
                {inv.vessels.map((v) => (
                  <tr key={v.mmsi} className={v.mmsi === selectedMmsi ? "sel" : ""} onClick={() => onSelectVessel(v.mmsi)}>
                    <td><b>{v.name || v.mmsi}</b><br /><span style={{ color: "var(--mut)", fontFamily: "var(--mono)", fontSize: 10.5 }}>{v.mmsi}</span></td>
                    <td><span className="type-chip">{v.vessel_type || "—"}</span></td>
                    <td>{v.track_points.length}</td>
                    <td>{v.ais_gaps?.length || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {status.attribution !== "done" && (
              <StageButton label="Rank Vessels" running={status.attribution === "running"} onClick={actions.rankVessels} disabled={status.vessels !== "done"} />
            )}
            {err("attribution")}
          </div>
        </>
      )}

      {/* ---------- attribution ---------- */}
      {att && (
        <>
          <div className="panel-h">TOP CANDIDATE</div>
          {att.no_strong_candidate && (
            <div className="pcard tint"><h3>No strong candidate</h3>
              <p style={{ fontSize: 12.5, color: "var(--mut)" }}>
                No vessel reached the evidence threshold. Ranked candidates below are shown for investigator review only.
              </p></div>
          )}
          {selectedCandidate && (
            <div className="pcard">
              <div className="vessel-head">
                <div className="vessel-ico">
                  <svg width="26" height="26" viewBox="0 0 26 26"><path d="M4 16l3-7h12l3 7c-2.4 2.2-5.6 3.4-9 3.4S6.4 18.2 4 16z" fill="#22b8d4" /><rect x="11" y="5" width="4" height="5" fill="#8fa3b8" /></svg>
                </div>
                <div>
                  <h3 style={{ margin: 0 }}>{selectedCandidate.vessel_name || selectedCandidate.vessel_mmsi}</h3>
                  <span className="type-chip">{selectedCandidate.vessel_type || "Vessel"}</span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--mut)", marginLeft: 8 }}>MMSI {selectedCandidate.vessel_mmsi}</span>
                </div>
              </div>
              <div className="panel-h" style={{ margin: "8px 0 2px" }}>ATTRIBUTION SCORE</div>
              <div className="score-row">
                <span className="score-big">{selectedCandidate.overall_score.toFixed(2)}</span>
                <ConfChip conf={selectedCandidate.confidence} />
              </div>
              <Bar name="Spatial compatibility" score={selectedCandidate.spatial_score * 100} />
              <Bar name="Temporal compatibility" score={selectedCandidate.temporal_score * 100} />
              <Bar name="Trajectory compatibility" score={selectedCandidate.trajectory_score * 100} />
              <Bar name="AIS data reliability" score={selectedCandidate.ais_reliability_score * 100} />
              <div className="kv"><span className="k">Behavioural anomaly</span><span className="v" style={{ color: "var(--mut)", fontWeight: 500 }}>Detection not currently enabled</span></div>
              <div className="kv"><span className="k">Min distance to source</span><span className="v">{selectedCandidate.min_distance_km.toFixed(2)} km</span></div>
              <div className="kv"><span className="k">Estimated release</span><span className="v" style={{ fontSize: 11.5 }}>{selectedCandidate.release_location.lat.toFixed(3)}°N, {selectedCandidate.release_location.lon.toFixed(3)}°E<br />{fmtUtc(selectedCandidate.release_time_utc)}</span></div>
              <div className="notice"><Info />Compatibility score — not a probability of responsibility.</div>
              {status.forward !== "done" && (
                <StageButton label="Run Forward Simulation" running={status.forward === "running"} onClick={actions.runForward}
                  disabled={!selectedCandidate.forward_request} />
              )}
              {err("forward")}
            </div>
          )}

          <div className="panel-h">RANKED CANDIDATES</div>
          <div className="pcard" style={{ padding: 8 }}>
            <table className="cand-table">
              <thead><tr><th>#</th><th>VESSEL</th><th>SCORE</th></tr></thead>
              <tbody>
                {att.all_attributions.map((a) => {
                  const v = vesselByMmsi[a.mmsi];
                  const isTop = (att.top_candidates || []).some((t) => t.vessel_mmsi === a.mmsi);
                  return (
                    <tr key={a.mmsi} className={a.mmsi === selectedMmsi ? "sel" : ""}
                      onClick={() => isTop && onSelectVessel(a.mmsi)}
                      style={isTop ? {} : { opacity: 0.65, cursor: "default" }}>
                      <td>{a.rank}</td>
                      <td><b>{v?.name || a.mmsi}</b><br /><span style={{ color: "var(--mut)", fontSize: 10.5 }}>{v?.vessel_type || ""}</span></td>
                      <td><b>{a.overall_score.toFixed(2)}</b></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ---------- forward + counterfactual ---------- */}
      {inv.forward && (
        <>
          <div className="panel-h">FORWARD SIMULATION</div>
          <div className="pcard">
            <div className="kv"><span className="k">Particles</span><span className="v">{inv.forward.simulation_metadata.particle_count}</span></div>
            <div className="kv"><span className="k">Duration</span><span className="v">{inv.forward.simulation_metadata.duration_hours.toFixed(1)} h</span></div>
            <div className="kv"><span className="k">Oil type</span><span className="v">{inv.forward.simulation_metadata.oil_type}</span></div>
            <div className="notice"><Info />Predicted footprint is a simulated particle envelope — not an observed slick.</div>
            {status.counterfactual !== "done" && (
              <StageButton label="Compare With Observed Slick" running={status.counterfactual === "running"} onClick={actions.runCounterfactual} />
            )}
            {err("counterfactual")}
          </div>
        </>
      )}

      {cf && (
        <>
          <div className="panel-h">COUNTERFACTUAL EVIDENCE</div>
          <div className="pcard tint">
            <div className="kv"><span className="k">Spatial agreement (Jaccard)</span><span className="v">{(cf.spatial_agreement * 100).toFixed(1)}%</span></div>
            <div className="kv"><span className="k">Trajectory reaches observed slick</span><span className="v">{cf.trajectory_reaches_slick ? "YES" : "NO"}</span></div>
            <div className="kv"><span className="k">Centroid distance</span><span className="v">{cf.centroid_distance_km.toFixed(2)} km</span></div>
            <div className="kv"><span className="k">Evidence strength</span>
              <span className={`v strength-${(cf.evidence_strength || "none").toLowerCase()}`}>{(cf.evidence_strength || "—").toUpperCase()}</span></div>
            {cf.explanation && <p style={{ fontSize: 12, color: "var(--mut)", lineHeight: 1.5, marginBottom: 0 }}>{cf.explanation}</p>}
            <div className="notice"><Info />Geometric overlap indicators — not probabilities of responsibility.</div>
          </div>

          <div className="panel-h">INVESTIGATION SUMMARY</div>
          <div className="pcard">
            <div className="summary-grid">
              <div className="cell"><span>Observed slick</span><b>{fmtUtc(inv.slick.timestamp_utc)}</b></div>
              <div className="cell"><span>Area</span><b>{inv.slick.area_km2.toFixed(1)} km²</b></div>
              <div className="cell"><span>Top candidate</span><b>{inv.forwardCandidate?.vessel_name || inv.forward.vessel_mmsi}</b></div>
              <div className="cell"><span>MMSI</span><b>{inv.forward.vessel_mmsi}</b></div>
              <div className="cell"><span>Attribution score</span><b>{inv.forwardCandidate?.overall_score.toFixed(2)}</b></div>
              <div className="cell"><span>Confidence</span><b>{inv.forwardCandidate?.confidence}</b></div>
              <div className="cell"><span>Est. release</span><b>{fmtUtc(inv.forward.release_time_utc)}</b></div>
              <div className="cell"><span>Evidence strength</span><b className={`strength-${(cf.evidence_strength || "none").toLowerCase()}`}>{cf.evidence_strength}</b></div>
            </div>
            <div className="disclaimer">
              These outputs are model-based geometric and physical-consistency
              evidence and should not be interpreted as proof of responsibility.
            </div>
          </div>
        </>
      )}
    </aside>
  );
}
