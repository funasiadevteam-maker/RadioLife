// Phase Π.4 — React Error Boundary.
//
// Wraps the entire app shell.  Catches render-time errors that React
// can't recover from, shows a friendly "Something went wrong" page,
// and POSTs the stack trace to /api/telemetry/error so we get a Mongo
// trail even before Sentry is hooked up.
import React from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, info: null, reported: false };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    this.setState({ info });
    // Best-effort telemetry — never throw inside catch.
    (async () => {
      try {
        await axios.post(`${API}/telemetry/error`, {
          message:          String(error?.message || error),
          stack:              String(error?.stack || "").slice(0, 4000),
          component_stack: String(info?.componentStack || "").slice(0, 4000),
          url:                  typeof window !== "undefined" ? window.location.href : "",
          user_agent:    typeof navigator !== "undefined" ? navigator.userAgent : "",
        }, { withCredentials: true, timeout: 4000 });
        this.setState({ reported: true });
      } catch (_e) { /* swallow */ }
    })();
  }
  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div data-testid="error-boundary"
                style={{
                    minHeight: "100vh", display: "grid", placeItems: "center",
                    background: "#0a0a0d", color: "#e5e7eb",
                    fontFamily: "ui-sans-serif, system-ui, -apple-system",
                    padding: 24,
                }}>
        <div style={{ maxWidth: 520, textAlign: "center" }}>
          <div style={{ fontSize: 48, lineHeight: 1, marginBottom: 12 }}>⚡</div>
          <h1 style={{ fontSize: 28, fontWeight: 800, margin: "0 0 8px" }}>
            Something went wrong
          </h1>
          <p style={{ color: "#9aa3af", marginBottom: 24, lineHeight: 1.55 }}>
            We&apos;ve been notified and the team will take a look. In the
            meantime, you can reload the page or head back to the BigFM home.
          </p>
          <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
            <button onClick={() => window.location.reload()}
                            data-testid="error-boundary-reload"
                            style={btnPrimary}>Reload</button>
            <a href="/" data-testid="error-boundary-home"
                  style={{ ...btnSecondary, textDecoration: "none" }}>BigFM home</a>
          </div>
          {this.state.reported && (
            <div style={{ marginTop: 14, fontSize: 11, color: "#6b7280" }}>
              Report ID logged to BigFM telemetry.
            </div>
          )}
        </div>
      </div>
    );
  }
}

const btnPrimary = {
  padding: "10px 16px", borderRadius: 999,
  background: "#fbbf24", color: "#0a0a0d", fontWeight: 700,
  border: 0, cursor: "pointer", fontSize: 14,
};
const btnSecondary = {
  padding: "10px 16px", borderRadius: 999,
  background: "transparent", color: "#e5e7eb", fontWeight: 600,
  border: "1px solid rgba(255,255,255,0.15)", cursor: "pointer", fontSize: 14,
};
