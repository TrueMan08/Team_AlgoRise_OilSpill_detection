import { BACKEND_BASE_URL } from "../api.js";

const Drop = ({ s = 40 }) => (
  <svg width={s} height={s} viewBox="0 0 32 32">
    <circle cx="16" cy="16" r="15" fill="#12263d" stroke="#2a4a72" />
    <path d="M16 6c4 5 7 8.5 7 12a7 7 0 1 1-14 0c0-3.5 3-7 7-12z" fill="#22b8d4" />
  </svg>
);

export default function Landing({ backend, onDemo, onNew }) {
  return (
    <div className="landing">
      <div className="landing-card">
        <div className="mark">
          <Drop s={52} />
          <div>
            <h1>OilTrace</h1>
            <div style={{ color: "#9fc3e0", fontSize: 13, letterSpacing: "0.08em" }}>
              MARINE SPILL INTELLIGENCE
            </div>
          </div>
        </div>
        <p className="tag">
          Detect an oil slick from satellite radar, trace its drift backward to a
          probable source region, search historic AIS tracks, rank candidate
          vessels on physical evidence — and test the hypothesis with a forward
          simulation.
        </p>
        <div className="actions">
          <button className="btn btn-demo" onClick={onDemo}>
            ▶&nbsp; Launch Norway Demo Scenario
          </button>
          <button className="btn btn-new" onClick={onNew}>
            + &nbsp;New Investigation
          </button>
        </div>
        <div className="backend-line">
          backend&nbsp;
          {backend === "online" ? "● connected" : backend === "checking" ? "○ checking…" : "○ starting / unreachable"}
          &nbsp;·&nbsp;{BACKEND_BASE_URL}
        </div>
        <p className="foot">
          Demo scenario uses synthetic AIS data and archived Sentinel-1 imagery
          (Trujillo-Acatitla et al., Zenodo, CC-BY 4.0). All analytical outputs —
          source regions, rankings, trajectories — are computed live by the
          OilTrace backend. Model outputs are physical-consistency evidence, not
          proof of responsibility. · Team AlgoRise — SIH 2026 (SIH26143)
        </p>
      </div>
    </div>
  );
}
