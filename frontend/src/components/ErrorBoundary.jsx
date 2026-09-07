import { Component } from "react";

/**
 * Without a boundary, a throw in any panel unmounts the whole tree and the
 * operator is left staring at a blank page mid-investigation. This contains
 * the failure, shows what broke, and offers a reload.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("OilTrace UI crashed:", error, info?.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        role="alert"
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "32px",
          background: "#f8fafc",
          fontFamily: "Inter, system-ui, sans-serif",
          color: "#0f172a",
        }}
      >
        <div style={{ maxWidth: "560px" }}>
          <h1 style={{ fontSize: "18px", fontWeight: 800, margin: "0 0 8px" }}>
            The interface hit an unexpected error
          </h1>
          <p style={{ fontSize: "13px", lineHeight: 1.5, color: "#475569", margin: "0 0 16px" }}>
            The investigation state was not saved. Reload to start a new case.
          </p>
          <pre
            style={{
              fontSize: "11.5px",
              fontFamily: "monospace",
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: "8px",
              padding: "12px",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              color: "#b91c1c",
              margin: "0 0 16px",
            }}
          >
            {error?.message || String(error)}
          </pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              background: "#0f172a",
              color: "#ffffff",
              border: "none",
              borderRadius: "8px",
              padding: "10px 18px",
              fontSize: "13px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
