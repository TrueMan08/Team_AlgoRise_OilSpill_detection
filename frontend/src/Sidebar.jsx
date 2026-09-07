import "./Sidebar.css";
import {
  Droplets,
  ScanLine,
  Ship,
  FileText,
  CirclePlay,
  Map,
} from "lucide-react";

const NAV = [
  { id: "incident", label: "Incident", Icon: ScanLine },
  { id: "detect", label: "Detection", Icon: Droplets },
  { id: "vessels", label: "Vessels", Icon: Ship },
  { id: "evidence", label: "Evidence", Icon: FileText },
  { id: "replay", label: "Replay", Icon: CirclePlay },
  { id: "map", label: "Scene", Icon: Map },
];

function Sidebar({
  activeItem,
  onSelect,
  backendOnline,
}) {

  return (
    <aside className="oiltrace-sidebar command-nav stitch-nav" aria-label="OilTrace navigation">
      <div className="sidebar-brand stitch-brand">
        <div className="brand-mark stitch-drop" aria-hidden="true">
          <Droplets size={18} color="#fff" strokeWidth={2.4} />
        </div>
        <div className="brand-text">
          <strong className="brand-name">OilTrace</strong>
        </div>
      </div>

      <nav className="sidebar-navigation">
        {NAV.map((item) => {
          const Icon = item.Icon;
          return (
            <button
              key={item.id}
              type="button"
              className={`sidebar-item ${activeItem === item.id ? "active" : ""}`}
              onClick={() => onSelect?.(item.id)}
            >
              <span className="sidebar-icon">
                <Icon size={20} strokeWidth={1.75} />
              </span>
              <span className="sidebar-label">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <button type="button" className="stitch-rail-chevron" tabIndex={-1} aria-hidden="true">
        <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
          <path d="M8 2 L4 6 L8 10" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <div className="sidebar-footer command-user stitch-nav-foot">
        <div className={`stitch-mission ${backendOnline === false ? "is-off" : ""}`}>
          <span className={`demo-dot ${backendOnline === false ? "offline" : ""}`} />
          <div>
            <strong>SIH 26143</strong>
            <small>{backendOnline === false ? "Watch floor offline" : "NTRO · E. Med"}</small>
          </div>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
