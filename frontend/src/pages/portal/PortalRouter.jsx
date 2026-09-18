// Phase PORTAL.0 — PortalRoleRouter.
// Route: /portal — authenticate FIRST, then resolve the access context, then
// pick a destination. Never invents access behavior from the design variant;
// it consumes the shared /api/portal/context (via usePortalAccess).
//
// Flow:  authed? → resolve workspaces →
//          0 workspaces  → consumer home ("/")
//          1 workspace   → that workspace's route
//          many          → workspace chooser (V2 premium / themed) unless a
//                          valid active workspace is already stored.
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Store, ShieldCheck, Megaphone, ChevronRight } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { usePortalAccess } from "@/hooks/usePortalAccess";
import "@/design_v2/newlookv2.css";

const ICONS = { admin: ShieldCheck, merchant: Store, advertiser: Megaphone };

export default function PortalRouter() {
  const navigate = useNavigate();
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user, loading: authLoading } = useAuth();

  const loaded = usePortalAccess((s) => s.loaded);
  const loading = usePortalAccess((s) => s.loading);
  const workspaces = usePortalAccess((s) => s.workspaces);
  const activeWorkspaceId = usePortalAccess((s) => s.activeWorkspaceId);
  const needsChoice = usePortalAccess((s) => s.needsChoice);
  const recommendedRoute = usePortalAccess((s) => s.recommendedRoute);
  const fetchAccess = usePortalAccess((s) => s.fetch);
  const setActive = usePortalAccess((s) => s.setActive);

  // Not signed in → unified portal login.
  useEffect(() => {
    if (!authLoading && !user) navigate("/portal/login", { replace: true });
  }, [authLoading, user, navigate]);

  // Load context once we know who the user is.
  useEffect(() => {
    if (user && !loaded && !loading) fetchAccess();
  }, [user, loaded, loading, fetchAccess]);

  // Auto-route when unambiguous (no choice needed, or an active workspace is set).
  useEffect(() => {
    if (!loaded) return;
    if (workspaces.length === 0) { navigate("/", { replace: true }); return; }
    const active = workspaces.find((w) => w.id === activeWorkspaceId);
    if (!needsChoice || active) {
      const dest = active ? active.route : recommendedRoute;
      navigate(dest || "/", { replace: true });
    }
  }, [loaded, workspaces, activeWorkspaceId, needsChoice, recommendedRoute, navigate]);

  const choose = (w) => {
    setActive(w.id);
    navigate(w.route || "/", { replace: true });
  };

  const showChooser = loaded && workspaces.length > 1 && needsChoice
    && !workspaces.find((w) => w.id === activeWorkspaceId);

  if (!showChooser) {
    return (
      <div className={`min-h-screen flex items-center justify-center ${
                          variant === "new_look_v2" ? "nlv2" : light ? "bg-purple-50" : "bg-slate-950"}`}
                data-testid="portal-router-loading">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={30} className="animate-spin"
                            style={{ color: variant === "new_look_v2" ? "#a855f7" : light ? "#7c3aed" : "#22d3ee" }} />
          <span className="text-[11px] font-mono uppercase tracking-widest"
                      style={{ color: "#8b96b8" }}>Resolving your access…</span>
        </div>
      </div>
    );
  }

  // Workspace chooser.
  const wrap = variant === "new_look_v2"
    ? "nlv2 min-h-screen flex items-center justify-center p-4"
    : `min-h-screen flex items-center justify-center p-4 ${light ? "bg-purple-50" : "bg-slate-950"}`;
  const card = variant === "new_look_v2"
    ? "w-full max-w-md nlv2-glass-strong rounded-3xl p-7"
    : `w-full max-w-md rounded-3xl p-7 ${light ? "bg-white border border-slate-100" : "bg-slate-900 border border-slate-800"}`;

  return (
    <div className={wrap} data-testid="portal-workspace-chooser">
      <div className={card}>
        <div className="text-center mb-5">
          <div className={`font-black text-xl ${light && variant !== "new_look_v2" ? "text-slate-900" : "text-white"}`}>
            Choose a workspace
          </div>
          <div className="text-[11px] font-mono uppercase tracking-widest mt-1" style={{ color: "#8b96b8" }}>
            You belong to {workspaces.length} workspaces
          </div>
        </div>
        <div className="space-y-2">
          {workspaces.map((w) => {
            const Icon = ICONS[w.type] || Store;
            return (
              <button key={`${w.type}-${w.id}`} onClick={() => choose(w)}
                            data-testid={`portal-workspace-${w.id}`}
                            className={`w-full flex items-center gap-3 rounded-2xl p-3 text-left transition ${
                              variant === "new_look_v2" ? "nlv2-glass hover:brightness-110"
                                : light ? "bg-slate-50 hover:bg-slate-100 border border-slate-100"
                                        : "bg-slate-800/60 hover:bg-slate-800 border border-slate-800"}`}>
                <span className="w-10 h-10 rounded-xl grid place-items-center shrink-0 text-white"
                            style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
                  <Icon size={18} />
                </span>
                <span className="flex-1 min-w-0">
                  <span className={`block text-sm font-bold truncate ${
                    light && variant !== "new_look_v2" ? "text-slate-900" : "text-white"}`}>
                    {w.name}
                  </span>
                  <span className="block text-[11px] capitalize" style={{ color: "#8b96b8" }}>
                    {w.role}{w.type === "merchant" ? " · merchant" : ""}
                  </span>
                </span>
                <ChevronRight size={16} style={{ color: "#8b96b8" }} />
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
