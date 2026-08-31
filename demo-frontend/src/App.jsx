import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { DEMO_INCIDENT_ID, DEMO_SLICK } from "./demo.js";
import { geomBounds, bboxString, shiftIso } from "./geo.js";
import Landing from "./components/Landing.jsx";
import Sidebar from "./components/Sidebar.jsx";
import TopBar from "./components/TopBar.jsx";
import MapView from "./components/MapView.jsx";
import RightPanel from "./components/RightPanel.jsx";
import Timeline from "./components/Timeline.jsx";
import SarPanel from "./components/SarPanel.jsx";

export const STAGES = [
  { id: "detection", num: "01", name: "Detection", sub: "Satellite oil spill detection" },
  { id: "hindcast", num: "02", name: "Hindcast", sub: "Backtrack probable source" },
  { id: "vessels", num: "03", name: "Vessels", sub: "Search AIS tracks" },
  { id: "attribution", num: "04", name: "Attribution", sub: "Rank candidate vessels" },
  { id: "forward", num: "05", name: "Forward Simulation", sub: "Test suspected release" },
  { id: "counterfactual", num: "06", name: "Counterfactual", sub: "Compare vs observed" },
];

const IDLE_STATUS = Object.fromEntries(STAGES.map((s) => [s.id, "idle"]));

const DEFAULT_LAYERS = {
  slick: true, source: true, backTraj: true, vessels: true,
  release: true, fwdTraj: true, footprint: true, particles: true,
};

export default function App() {
  const [showLanding, setShowLanding] = useState(true);
  const [showSar, setShowSar] = useState(false);
  const [inv, setInv] = useState({ incident_id: null });
  const [status, setStatus] = useState({ ...IDLE_STATUS });
  const [errors, setErrors] = useState({});
  const [activeStage, setActiveStage] = useState("detection");
  const [layers, setLayers] = useState({ ...DEFAULT_LAYERS });
  const [selectedMmsi, setSelectedMmsi] = useState(null);
  const [backend, setBackend] = useState("checking"); // online | warming | offline
  const [timeT, setTimeT] = useState(null); // active timeline ISO timestamp
  const [lookback, setLookback] = useState(12); // hindcast duration_hours

  // ---- backend health polling -------------------------------------------
  const pollHealth = useCallback(async () => {
    try {
      await api.health();
      setBackend("online");
    } catch {
      setBackend((b) => (b === "online" ? "warming" : "offline"));
    }
  }, []);
  useEffect(() => {
    pollHealth();
    const t = setInterval(pollHealth, 20000);
    return () => clearInterval(t);
  }, [pollHealth]);

  // ---- stage runner helper ----------------------------------------------
  const run = useCallback(async (stageId, fn) => {
    setStatus((s) => ({ ...s, [stageId]: "running" }));
    setErrors((e) => ({ ...e, [stageId]: null }));
    setActiveStage(stageId);
    try {
      await fn();
      setStatus((s) => ({ ...s, [stageId]: "done" }));
    } catch (err) {
      setStatus((s) => ({ ...s, [stageId]: "error" }));
      setErrors((e) => ({ ...e, [stageId]: err.message || String(err) }));
    }
  }, []);

  // ---- stage actions ----------------------------------------------------
  const loadDemo = useCallback(() => {
    setShowLanding(false);
    setInv({ incident_id: DEMO_INCIDENT_ID, slick: DEMO_SLICK, demo: true });
    setStatus({ ...IDLE_STATUS, detection: "done" });
    setErrors({});
    setSelectedMmsi(null);
    setTimeT(null);
    setActiveStage("detection");
    setLookback(2); // demo scenario: slick observed ~2 h after release
    setShowSar(true);
  }, []);

  const newInvestigation = useCallback(() => {
    setShowLanding(false);
    setInv({ incident_id: `incident-${Date.now()}`, demo: false });
    setStatus({ ...IDLE_STATUS });
    setErrors({});
    setActiveStage("detection");
  }, []);

  const reset = useCallback(() => {
    setInv({ incident_id: null });
    setStatus({ ...IDLE_STATUS });
    setErrors({});
    setSelectedMmsi(null);
    setTimeT(null);
    setShowLanding(true);
  }, []);

  const runHindcast = useCallback(() =>
    run("hindcast", async () => {
      const res = await api.hindcast(inv.slick, lookback);
      setInv((v) => ({ ...v, hindcast: res }));
    }), [inv.slick, lookback, run]);

  const findVessels = useCallback(() =>
    run("vessels", async () => {
      const hc = inv.hindcast;
      const geoms = [
        inv.slick.geometry,
        ...hc.source_region.candidate_regions.map((c) => c.geometry),
      ];
      const b = geomBounds(geoms);
      const bbox = bboxString(b, 0.6);
      // Release window from candidate regions, expanded ±12 h (high recall).
      const starts = hc.source_region.candidate_regions.map((c) => c.start_time_utc);
      const ends = hc.source_region.candidate_regions.map((c) => c.end_time_utc);
      const start = shiftIso(starts.sort()[0], -12);
      const end = shiftIso(ends.sort().slice(-1)[0], 12);
      const res = await api.vessels(bbox, start, end);
      setInv((v) => ({ ...v, vessels: res, vesselQuery: { bbox, start, end } }));
    }), [inv.hindcast, inv.slick, run]);

  const rankVessels = useCallback(() =>
    run("attribution", async () => {
      const res = await api.attribute(
        inv.incident_id, inv.hindcast.source_region, inv.vessels, null
      );
      setInv((v) => ({ ...v, attribution: res }));
      const top = res.top_candidates?.[0];
      if (top) setSelectedMmsi(top.vessel_mmsi);
    }), [inv, run]);

  const selectedCandidate = useMemo(() => {
    const tops = inv.attribution?.top_candidates || [];
    return tops.find((c) => c.vessel_mmsi === selectedMmsi) || tops[0] || null;
  }, [inv.attribution, selectedMmsi]);

  const runForward = useCallback(() =>
    run("forward", async () => {
      const fr = selectedCandidate.forward_request;
      const res = await api.forward(fr);
      setInv((v) => ({ ...v, forward: res, forwardCandidate: selectedCandidate }));
      if (res.trajectory_timestamps_utc?.length) setTimeT(res.trajectory_timestamps_utc[0]);
    }), [run, selectedCandidate]);

  const runCounterfactual = useCallback(() =>
    run("counterfactual", async () => {
      const res = await api.counterfactual(
        inv.incident_id, inv.forward.vessel_mmsi, inv.forward, inv.slick
      );
      setInv((v) => ({ ...v, counterfactual: res }));
    }), [inv, run]);

  const actions = { loadDemo, newInvestigation, reset, runHindcast, findVessels, rankVessels, runForward, runCounterfactual };

  if (showLanding) return <Landing backend={backend} onDemo={loadDemo} onNew={newInvestigation} />;

  return (
    <div className="shell">
      <Sidebar
        stages={STAGES} status={status} activeStage={activeStage}
        onStage={setActiveStage} layers={layers}
        onToggle={(k) => setLayers((l) => ({ ...l, [k]: !l[k] }))}
      />
      <TopBar inv={inv} backend={backend} status={status} onReset={reset} />
      <div className="mapwrap">
        <MapView
          inv={inv} layers={layers} selectedMmsi={selectedMmsi}
          onSelectVessel={setSelectedMmsi} timeT={timeT}
          onOpenSar={() => setShowSar(true)}
        />
        {showSar && inv.slick && <SarPanel slick={inv.slick} onClose={() => setShowSar(false)} />}
      </div>
      <RightPanel
        inv={inv} status={status} errors={errors} activeStage={activeStage}
        actions={actions} selectedMmsi={selectedMmsi} onSelectVessel={setSelectedMmsi}
        selectedCandidate={selectedCandidate} backend={backend}
        lookback={lookback} onLookback={setLookback}
      />
      <Timeline inv={inv} timeT={timeT} onTime={setTimeT} />
    </div>
  );
}
