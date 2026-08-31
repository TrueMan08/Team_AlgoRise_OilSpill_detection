import { useEffect, useMemo, useRef, useState } from "react";
import { fmtClock, fmtUtc } from "../geo.js";

// Temporal analysis strip. Timestamps come EXACTLY from the backend:
// forward trajectory timestamps when available, otherwise the (reversed)
// backward hindcast timestamps. We never generate our own timestamps.
export default function Timeline({ inv, timeT, onTime }) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const railRef = useRef(null);
  const timeRef = useRef(timeT);
  timeRef.current = timeT;

  const times = useMemo(() => {
    if (inv.forward?.trajectory_timestamps_utc?.length)
      return inv.forward.trajectory_timestamps_utc;
    if (inv.hindcast?.trajectory_timestamps_utc?.length)
      return [...inv.hindcast.trajectory_timestamps_utc].sort();
    return [];
  }, [inv.forward, inv.hindcast]);

  const t0 = times.length ? new Date(times[0]).getTime() : 0;
  const t1 = times.length ? new Date(times[times.length - 1]).getTime() : 0;
  const cur = timeT ? new Date(timeT).getTime() : t0;
  const frac = t1 > t0 ? Math.min(1, Math.max(0, (cur - t0) / (t1 - t0))) : 0;

  // Smooth playback: requestAnimationFrame interpolates continuously between
  // the backend-provided timestamps (1× plays the whole simulation in ~14 s).
  // The clock lives in a local variable — deriving it from React state each
  // frame lags a render behind and makes the cursor stall then leap.
  useEffect(() => {
    if (!playing || times.length < 2) return;
    let raf, last = performance.now();
    let cur2 = timeRef.current ? new Date(timeRef.current).getTime() : t0;
    if (cur2 >= t1 - 500) cur2 = t0; // restart when played from the end
    const rate = ((t1 - t0) / 14000) * speed;
    const tick = (now) => {
      cur2 = Math.min(t1, cur2 + (now - last) * rate);
      last = now;
      onTime(new Date(cur2).toISOString());
      if (cur2 >= t1) { setPlaying(false); return; }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, times, t0, t1, onTime]);

  if (!times.length)
    return (
      <div className="timeline">
        <div className="tl-head"><span className="tl-title">TEMPORAL ANALYSIS (UTC)</span></div>
        <div className="tl-empty">
          Timestamps appear here after the backward hindcast — and animate the
          forward simulation once it runs.
        </div>
      </div>
    );

  const release = inv.forward?.release_time_utc;
  const obs = inv.slick?.timestamp_utc;
  // nearest backend-timestamp index to the current (possibly interpolated) time
  const nearIdx = () => {
    const t = timeT ? new Date(timeT).getTime() : t0;
    let best = 0, bd = Infinity;
    times.forEach((x, i) => {
      const d = Math.abs(new Date(x).getTime() - t);
      if (d < bd) { bd = d; best = i; }
    });
    return best;
  };
  const seek = (e) => {
    const rect = railRef.current.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const target = t0 + f * (t1 - t0);
    // snap to nearest backend timestamp
    let best = times[0], bd = Infinity;
    for (const ts of times) {
      const d = Math.abs(new Date(ts).getTime() - target);
      if (d < bd) { bd = d; best = ts; }
    }
    onTime(best);
  };

  return (
    <div className="timeline">
      <div className="tl-head">
        <span className="tl-title">TEMPORAL ANALYSIS (UTC)</span>
        <span style={{ fontSize: 10, color: "var(--mut)" }}>playback interpolates hourly model timesteps</span>
        {release && <span className="tl-release">Release · {fmtUtc(release)}</span>}
        {obs && <span className="tl-obs">Observation · {fmtUtc(obs)}</span>}
      </div>
      <div className="tl-rail-wrap" ref={railRef} onClick={seek} style={{ cursor: "pointer" }}>
        <div className="tl-rail"><div className="tl-fill" style={{ width: `${frac * 100}%` }} /></div>
        <div className="tl-cursor" style={{ left: `${frac * 100}%` }}>
          <span className="flag">{fmtClock(timeT || times[0])}</span>
          <span className="knob" />
        </div>
      </div>
      <div className="tl-ticks">
        {times.filter((_, i) => i % Math.max(1, Math.floor(times.length / 7)) === 0)
          .map((ts) => <span key={ts}>{fmtClock(ts)}</span>)}
      </div>
      <div className="tl-controls">
        <button onClick={() => { setPlaying(false); onTime(times[0]); }} title="Reset">⏮</button>
        <button onClick={() => { setPlaying(false); onTime(times[Math.max(0, nearIdx() - 1)]); }} title="Step back">◀</button>
        <button className="play" onClick={() => setPlaying((p) => !p)} title="Play / pause">
          {playing ? "❚❚" : "▶"}
        </button>
        <button onClick={() => { setPlaying(false); onTime(times[Math.min(times.length - 1, nearIdx() + 1)]); }} title="Step forward">▶▐</button>
        <button onClick={() => { setPlaying(false); onTime(times[times.length - 1]); }} title="Show full trajectory">⏭</button>
        <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}
          style={{ border: "1px solid var(--line)", borderRadius: 8, height: 30, fontFamily: "var(--sans)", fontSize: 12 }}>
          <option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option>
        </select>
      </div>
    </div>
  );
}
