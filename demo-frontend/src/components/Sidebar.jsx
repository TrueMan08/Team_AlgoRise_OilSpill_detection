const LAYER_DEFS = [
  { key: "slick", name: "Observed Slick", swatch: "#e8862e" },
  { key: "source", name: "Source Region (prob. mass)", swatch: "#3b76d2" },
  { key: "backTraj", name: "Backward Trajectory", swatch: "#1899b8", dashed: true },
  { key: "vessels", name: "AIS Vessel Tracks", swatch: "#7a8ea1" },
  { key: "release", name: "Estimated Release", swatch: "#d92f23" },
  { key: "fwdTraj", name: "Forward Trajectory", swatch: "#7a3fd1", dashed: true },
  { key: "footprint", name: "Predicted Footprint", swatch: "#17a08b" },
  { key: "particles", name: "Drift Particles (sim)", swatch: "#3a4552" },
];

function StepState({ st }) {
  if (st === "done") return <span className="dot-done">✓</span>;
  if (st === "running") return <span className="spinner" />;
  if (st === "error") return <span className="dot-err">!</span>;
  return <span className="dot-idle" />;
}

export default function Sidebar({ stages, status, activeStage, onStage, layers, onToggle }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">
          <svg width="22" height="22" viewBox="0 0 32 32">
            <path d="M16 4c4.6 5.8 8 9.9 8 14a8 8 0 1 1-16 0c0-4.1 3.4-8.2 8-14z" fill="#22b8d4" />
          </svg>
        </div>
        <div>
          <h1>OilTrace<span>Marine Spill Intelligence</span></h1>
        </div>
      </div>

      <div className="side-label">INVESTIGATION WORKFLOW</div>
      <div className="steps">
        {stages.map((s) => (
          <button
            key={s.id}
            className={`step ${activeStage === s.id ? "active" : ""}`}
            onClick={() => onStage(s.id)}
          >
            <span className="step-num">{s.num}</span>
            <span>
              <span className="step-name">{s.name}</span>
              <span className="step-sub" style={{ display: "block" }}>{s.sub}</span>
            </span>
            <span className="step-state"><StepState st={status[s.id]} /></span>
          </button>
        ))}
      </div>

      <div className="side-label">MAP LAYERS</div>
      <div className="layers">
        {LAYER_DEFS.map((l) => (
          <div className="layer-row" key={l.key}>
            <span
              className="layer-key"
              style={l.dashed
                ? { border: `2px dashed ${l.swatch}`, background: "none", height: 0, borderRadius: 0, borderBottom: "none", borderLeft: "none", borderRight: "none" }
                : { background: l.swatch, opacity: 0.85 }}
            />
            <span className="name">{l.name}</span>
            <button
              className={`toggle ${layers[l.key] ? "on" : ""}`}
              aria-label={`toggle ${l.name}`}
              onClick={() => onToggle(l.key)}
            />
          </div>
        ))}
      </div>

      <div className="side-foot">
        <b>Evidence, not accusation.</b><br />
        Scores and regions are model-based physical-consistency evidence — never
        proof of responsibility.
      </div>
    </aside>
  );
}
