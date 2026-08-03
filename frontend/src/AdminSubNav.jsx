// Phase ADMIN.NAV.1 — AdminSubNav deprecated in favour of the unified
// AdminSidebar (see components/AdminSidebar.jsx).
//
// This module used to render a 220px secondary rail inside each admin
// page (~10-15 call sites).  The AppShell now left-pads its content
// area by 220px on `/admin/*` routes to make room for the unified
// AdminSidebar, so this component just returns null — every existing
// admin page continues to work without per-file edits.
export default function AdminSubNav() {
  return null;
}
