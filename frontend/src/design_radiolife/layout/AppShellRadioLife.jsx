// Phase R.1 — RadioLife app shell.  Light-mode container + optional
// bottom nav.  Screens can opt out of the bottom nav (e.g. Now Playing,
// Restaurant Detail) by passing showBottomNav={false}.
import React from "react";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";
import BottomNavRadioLife from "./BottomNavRadioLife";
import { Sparkles } from "lucide-react";

export default function AppShellRadioLife({
  children,
  showBottomNav = true,
  bare = false,
  className = "",
}) {
  const setVariant = useDesignVariantStore((s) => s.setVariant);
  return (
    <div
      data-testid="rl-app-shell"
      className={"rl-root min-h-screen text-slate-900 " + className}
      style={{ background: "#FBF5EC", fontFamily: "'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif" }}>
      {/* Fixed floating toggle to return to legacy — visible on every RadioLife screen. */}
      {!bare && (
        <button
          type="button"
          onClick={() => setVariant("legacy")}
          data-testid="rl-return-to-legacy"
          className="fixed top-3 right-3 z-50 h-8 px-3 rounded-full
                              bg-white/95 backdrop-blur border border-orange-100
                              text-orange-700 text-[11px] font-semibold uppercase
                              tracking-wider shadow-lg shadow-orange-500/10
                              hover:bg-orange-50 flex items-center gap-1.5">
          <Sparkles size={12} /> Legacy
        </button>
      )}
      <div className={"mx-auto max-w-md " + (showBottomNav ? "pb-24" : "pb-4")}>
        {children}
      </div>
      {showBottomNav && !bare && <BottomNavRadioLife />}
    </div>
  );
}
