export default function TopBar({ inv, backend, status, onReset }) {
  const anyRunning = Object.values(status).some((s) => s === "running");
  const allDone = status.counterfactual === "done";

  return (
    <header className="topbar">
      <div className="case-block">
        <span className="lbl">CASE</span>
        <span className="val">{(inv.incident_id || "—").toUpperCase()}</span>
      </div>

      {anyRunning ? (
        <span className="chip chip-warm"><span className="pulse" />ANALYSIS RUNNING</span>
      ) : allDone ? (
        <span className="chip chip-live"><span className="pulse" />INVESTIGATION COMPLETE</span>
      ) : (
        <span className="chip chip-live"><span className="pulse" />LIVE ANALYSIS</span>
      )}

      {inv.demo && (
        <span className="chip" style={{ background: "#eef2f8", color: "#4a5d72" }}>
          Demo / Synthetic AIS scenario
        </span>
      )}

      <div className="top-spacer" />

      <span className="top-note">
        Model outputs are spatial, temporal and physical-consistency evidence —
        not proof of vessel responsibility.
      </span>

      {backend === "online" ? (
        <span className="chip chip-live"><span className="pulse" />Backend Online</span>
      ) : backend === "checking" ? (
        <span className="chip chip-warm"><span className="pulse" />Checking…</span>
      ) : backend === "warming" ? (
        <span className="chip chip-warm"><span className="pulse" />Backend starting…</span>
      ) : (
        <span className="chip chip-off"><span className="pulse" />Backend Offline</span>
      )}

      <button className="scenario-chip" onClick={onReset} title="Back to start screen">
        ⟲ Reset
      </button>
    </header>
  );
}
