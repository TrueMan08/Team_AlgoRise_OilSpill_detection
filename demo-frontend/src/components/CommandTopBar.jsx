import { Bell, Search } from "lucide-react";

export default function CommandTopBar({
  incidentId,
  search,
  onSearch,
  onNewIncident,
  hasSyntheticAis = false,
}) {
  return (
    <header className="stitch-topbar">
      <nav className="stitch-crumbs" aria-label="Breadcrumb">
        <span>Incidents</span>
        <span aria-hidden="true">›</span>
        <strong>{incidentId}</strong>
        {hasSyntheticAis && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "2px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.04em",
              backgroundColor: "rgba(234, 88, 12, 0.15)",
              color: "#fb923c",
              border: "1px solid rgba(234, 88, 12, 0.35)",
              marginLeft: "12px",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: "#f97316",
              }}
            />
             SYNTHETIC AIS DATA
          </span>
        )}
      </nav>
      <label className="stitch-search">
        <Search size={16} strokeWidth={1.8} />
        <input
          type="search"
          value={search}
          onChange={(event) => onSearch?.(event.target.value)}
          placeholder="Search vessels, areas, incidents..."
          aria-label="Search vessels, areas, incidents"
        />
      </label>
      <div className="stitch-top-actions">
        <button type="button" className="stitch-new" onClick={onNewIncident}>
          + New incident
        </button>
        <button type="button" className="stitch-icon-btn" aria-label="Notifications">
          <Bell size={18} strokeWidth={1.8} />
          <span className="stitch-badge" />
        </button>
      </div>
    </header>
  );
}
