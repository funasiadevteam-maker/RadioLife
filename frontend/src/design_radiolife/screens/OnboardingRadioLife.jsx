// Phase R.1 — Onboarding.  Purple gradient hero + auth entry points.
// Reuses the existing /login flow — this is a re-skin only.
import React from "react";
import { Link } from "react-router-dom";
import { Radio, Sparkles } from "lucide-react";
import { RLButton } from "../DesignSystem";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";
import SignInWithGoogleButton from "@/SignInWithGoogleButton";

export default function OnboardingRadioLife() {
  const setVariant = useDesignVariantStore((s) => s.setVariant);
  return (
    <div className="min-h-screen relative overflow-hidden"
              data-testid="rl-onboarding">
      {/* Gradient hero background */}
      <div className="absolute inset-0"
                style={{ background: "linear-gradient(160deg, #A020F0 0%, #EC4899 55%, #FAF7FE 100%)" }} />
      {/* Big soft blob */}
      <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full
                              bg-white/20 blur-3xl pointer-events-none" />

      <div className="relative min-h-screen flex flex-col px-6 pt-10 pb-8
                              max-w-md mx-auto text-white">
        <button
          type="button"
          onClick={() => setVariant("legacy")}
          data-testid="rl-return-to-legacy"
          className="self-end h-8 px-3 rounded-full bg-white/25 backdrop-blur
                              text-white text-[11px] font-semibold uppercase tracking-wider
                              hover:bg-white/40 flex items-center gap-1.5">
          <Sparkles size={12} /> Try legacy
        </button>

        {/* Logo/mark */}
        <div className="mt-16 flex items-center gap-3">
          <div className="w-14 h-14 rounded-2xl bg-white/25 backdrop-blur
                                  flex items-center justify-center shadow-xl">
            <Radio size={28} className="text-white" />
          </div>
          <div className="font-black text-3xl tracking-tight">RadioLife</div>
        </div>

        {/* Hero copy */}
        <div className="mt-14">
          <h1 className="text-5xl font-black leading-[1.05] tracking-tight">
            Listen. Go out.<br />
            Pay. Earn.
          </h1>
          <p className="mt-5 text-white/85 text-base leading-relaxed max-w-sm">
            Personalised radio that pays you back — with real local deals
            near you, every day.
          </p>
        </div>

        <div className="flex-1" />

        {/* CTAs */}
        <div className="space-y-3">
          <SignInWithGoogleButton
            fullWidth
            size="large"
            variant="radiolife"
            redirectPath="/dashboard"
          />
          <Link to="/login" data-testid="rl-onboarding-email">
            <RLButton
              variant="ghost"
              size="lg"
              className="w-full bg-white text-purple-800 border-white
                                hover:bg-white hover:border-white shadow-xl">
              Continue with Email
            </RLButton>
          </Link>
          <Link to="/login" data-testid="rl-onboarding-phone">
            <RLButton
              variant="ghost"
              size="lg"
              className="w-full bg-white/15 backdrop-blur text-white
                                border-white/40 hover:bg-white/25 hover:border-white/60">
              Continue with Phone
            </RLButton>
          </Link>
          <div className="text-center text-white/70 text-xs mt-3">
            By continuing you agree to BigFM&apos;s{" "}
            <Link to="/terms" className="underline">Terms</Link> &{" "}
            <Link to="/privacy" className="underline">Privacy</Link>.
          </div>
        </div>
      </div>
    </div>
  );
}
