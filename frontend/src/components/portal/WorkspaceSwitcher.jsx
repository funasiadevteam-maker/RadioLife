// Phase PORTAL.0 — WorkspaceSwitcher.
// Design-independent workspace switching (owner / staff / cashier / admin /
// advertiser) with NO logout. The visual treatment adapts to the active
// variant; the underlying context + routing is shared (usePortalAccess).
// Renders nothing for plain consumers (0–1 workspaces).
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Store, ShieldCheck, Megaphone, Check, ChevronDown, LayoutGrid } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { usePortalAccess } from "@/hooks/usePortalAccess";

const ICONS = { admin: ShieldCheck, merchant: Store, advertiser: Megaphone };

export default function WorkspaceSwitcher({ compact = false }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const loaded = usePortalAccess((s) => s.loaded);
  const workspaces = usePortalAccess((s) => s.workspaces);
  const activeWorkspaceId = usePortalAccess((s) => s.activeWorkspaceId);
  const fetchAccess = usePortalAccess((s) => s.fetch);
  const setActive = usePortalAccess((s) => s.setActive);

  useEffect(() => {
    if (user && !loaded) fetchAccess();
  }, [user, loaded, fetchAccess]);

  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  // Only meaningful when the user actually has ≥1 non-consumer workspace.
  if (!user || !loaded || workspaces.length < 1) return null;

  const active = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0];

  const pick = (w) => {
    setActive(w.id);
    setOpen(false);
    navigate(w.route || "/");
  };

  return (
    <div className="relative" ref={ref} data-testid="workspace-switcher">
      <button type="button" onClick={() => setOpen((o) => !o)}
                    data-testid="workspace-switcher-trigger"
                    className="inline-flex items-center gap-1.5 h-9 px-2.5 rounded-full text-[#8b96b8] hover:text-white transition-colors"
                    style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" }}>
        <LayoutGrid size={15} />
        {!compact && (
          <span className="hidden md:block max-w-[120px] truncate text-[12px] font-bold text-white">
            {active?.name || "Workspace"}
          </span>
        )}
        <ChevronDown size={13} />
      </button>

      {open && (
        <div data-testid="workspace-switcher-menu"
                  className="absolute right-0 mt-2 w-64 rounded-2xl p-2 z-50 shadow-2xl"
                  style={{ background: "#141a2e", border: "1px solid rgba(255,255,255,0.1)" }}>
          <div className="px-2 py-1.5 text-[10px] font-mono uppercase tracking-widest" style={{ color: "#6b7392" }}>
            Switch workspace
          </div>
          {workspaces.map((w) => {
            const Icon = ICONS[w.type] || Store;
            const isActive = w.id === active?.id;
            return (
              <button key={`${w.type}-${w.id}`} onClick={() => pick(w)}
                            data-testid={`workspace-option-${w.id}`}
                            className="w-full flex items-center gap-2.5 rounded-xl p-2 text-left hover:bg-white/5 transition-colors">
                <span className="w-8 h-8 rounded-lg grid place-items-center shrink-0 text-white"
                            style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
                  <Icon size={15} />
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block text-[13px] font-bold text-white truncate">{w.name}</span>
                  <span className="block text-[10px] capitalize" style={{ color: "#8b96b8" }}>{w.role}</span>
                </span>
                {isActive && <Check size={15} className="text-[#f5c563]" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
