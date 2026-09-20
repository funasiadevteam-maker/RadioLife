// Admin-only design-variant control.
// Variant switching now lives ONLY in the admin backend — customers are
// locked to New Look V2. Design changes presentation only; it never changes
// access, permissions, or launch controls (backend is design-agnostic).
import { Link } from "react-router-dom";
import { Sparkles, Check, ArrowLeft, Palette } from "lucide-react";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";

const OPTIONS = [
  { key: "new_look_v2", label: "New Look V2", hint: "Premium dark cinematic — the customer-facing default", primary: true },
  { key: "radiolife",    label: "New Look (FUUSIC)", hint: "Light FUUSIC treatment" },
  { key: "classic_b",    label: "Classic B", hint: "New consumer nav shell" },
  { key: "legacy",          label: "Classic A (Legacy)", hint: "Original operational shell" },
];

export default function AdminAppearance() {
  const variant = useDesignVariantStore((s) => s.variant);
  const setVariant = useDesignVariantStore((s) => s.setVariant);

  return (
    <div className="min-h-screen bg-slate-950 text-white" data-testid="admin-appearance-page">
      <div className="max-w-3xl mx-auto p-6 sm:p-8">
        <Link to="/admin" data-testid="admin-appearance-back"
                    className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white mb-5">
          <ArrowLeft size={14} /> Admin Home
        </Link>

        <div className="flex items-center gap-3 mb-2">
          <span className="w-10 h-10 rounded-xl grid place-items-center bg-purple-500/15 text-purple-300">
            <Palette size={20} />
          </span>
          <div>
            <h1 className="text-2xl font-black tracking-tight">Appearance</h1>
            <p className="text-sm text-slate-400">Design variant (admin-only · QA). Customers always see New Look V2.</p>
          </div>
        </div>

        <div className="mt-6 space-y-3" data-testid="admin-appearance-options">
          {OPTIONS.map((o) => {
            const active = variant === o.key;
            return (
              <button key={o.key} type="button"
                            onClick={() => setVariant(o.key)}
                            data-testid={`admin-appearance-opt-${o.key}`}
                            className={`w-full flex items-center gap-4 rounded-2xl px-5 py-4 text-left border transition-colors ${
                              active
                                ? "border-purple-500 bg-purple-500/10"
                                : "border-slate-800 bg-slate-900 hover:border-slate-700"}`}>
                <span className={`w-10 h-10 rounded-xl grid place-items-center shrink-0 ${
                  o.primary ? "text-white" : "bg-slate-800 text-slate-300"}`}
                          style={o.primary ? { background: "linear-gradient(135deg,#A020F0,#EC4899)" } : undefined}>
                  <Sparkles size={16} />
                </span>
                <span className="flex-1 min-w-0">
                  <span className="flex items-center gap-2">
                    <span className="text-base font-black">{o.label}</span>
                    {o.primary && (
                      <span className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300">
                        Default
                      </span>
                    )}
                  </span>
                  <span className="block text-xs text-slate-400 mt-0.5">{o.hint}</span>
                </span>
                {active && <Check size={20} className="text-purple-400 shrink-0" data-testid={`admin-appearance-active-${o.key}`} />}
              </button>
            );
          })}
        </div>

        <p className="mt-6 text-xs text-slate-500">
          Your selection is remembered on this device only and applies to your admin browsing.
          It does not change what customers or staff see, and never bypasses Business Setup Mode
          or role permissions.
        </p>
      </div>
    </div>
  );
}
