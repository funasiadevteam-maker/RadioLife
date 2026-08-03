// Phase 19a Part 4 — shared breadcrumb for admin / advertiser sub-pages.
// Each segment except the last is a Link; the last is plain text marking
// the current page.  No shadcn dependency — minimal styled markup so the
// component is portable to advertiser pages too.
import React from "react";
import { Link } from "react-router-dom";

export default function AdminBreadcrumb({ segments, testid = "admin-breadcrumb" }) {
  if (!segments || segments.length === 0) return null;
  return (
    <nav data-testid={testid}
            aria-label="breadcrumb"
            style={{marginBottom: 14, fontSize: 12, color: "#9aa3af",
                        display: "flex", alignItems: "center", gap: 6,
                        flexWrap: "wrap"}}>
      {segments.map((s, i) => {
        const last = i === segments.length - 1;
        return (
          <React.Fragment key={`${s.label}-${i}`}>
            {last || !s.href ? (
              <span data-testid={`breadcrumb-segment-${i}`}
                        style={{color: last ? "#e7e7ea" : "#9aa3af",
                                    fontWeight: last ? 600 : 400}}>
                {s.label}
              </span>
            ) : (
              <Link to={s.href}
                        data-testid={`breadcrumb-segment-${i}`}
                        style={{color: "#9aa3af", textDecoration: "none"}}
                        onMouseEnter={(e) => { e.currentTarget.style.color = "#f59e0b"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.color = "#9aa3af"; }}>
                {s.label}
              </Link>
            )}
            {!last && <span style={{color: "#4b5563"}}>/</span>}
          </React.Fragment>
        );
      })}
    </nav>
  );
}
