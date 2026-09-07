const NEXT_STEP_COPY = [
  "No ranked vessel yet. Run hindcast to trace the slick back to its probable source region.",
  "Probable source region estimated. Run attribution to scan AIS traffic inside it and rank candidate vessels.",
  "Candidates ranked. Run counterfactual forward tests for the eligible vessels and compare their predicted drift with the observed slick.",
  "No ranked vessel selected.",
];

export default function OperationCard({ vessel, photoSrc, pipelineStage = 0 }) {
  if (!vessel) {
    return (
      <article className="op-card is-empty">
        <p>{NEXT_STEP_COPY[pipelineStage] || NEXT_STEP_COPY[0]}</p>
      </article>
    );
  }

  return (
    <article className="op-card">
      <img src={photoSrc} alt="" />
      <div className="op-card-body">
        <p className="op-kicker">{vessel.type || "Vessel"}</p>
        <h3>{vessel.name || vessel.mmsi}</h3>
        <p className="op-meta">MMSI {vessel.mmsi || vessel.id}</p>
        {Number.isFinite(Number(vessel.speedKnots)) && (
          <p className="op-meta">{Number(vessel.speedKnots).toFixed(1)} kn</p>
        )}
      </div>
    </article>
  );
}
