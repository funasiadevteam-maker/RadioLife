// P1 — reusable "N coupons left today" scarcity pill with a live
// countdown to the daily (UTC-midnight) reset. Used on the branded
// storefront and FPK game cards to create urgency.
import { useEffect, useState } from "react";
import { Flame, Clock, Infinity as InfinityIcon } from "lucide-react";

function useCountdown(resetsAt) {
  const [left, setLeft] = useState("");
  useEffect(() => {
    if (!resetsAt) return;
    const target = new Date(resetsAt).getTime();
    const tick = () => {
      const diff = Math.max(0, target - Date.now());
      const h = Math.floor(diff / 3.6e6);
      const m = Math.floor((diff % 3.6e6) / 6e4);
      const s = Math.floor((diff % 6e4) / 1000);
      setLeft(`${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [resetsAt]);
  return left;
}

export function CouponScarcityStrip({ remaining, resetsAt, accent = "#0aa54b", testId = "scarcity-strip" }) {
  const countdown = useCountdown(resetsAt);
  const unlimited = remaining === null || remaining === undefined;
  const soldOut = !unlimited && remaining <= 0;
  return (
    <div
      data-testid={testId}
      className="inline-flex items-center gap-3 rounded-full px-4 py-2 text-sm font-black"
      style={{
        background: soldOut ? "rgba(148,163,184,0.15)" : `${accent}1f`,
        color: soldOut ? "#94a3b8" : accent,
        border: `1px solid ${soldOut ? "rgba(148,163,184,0.35)" : accent + "55"}`,
      }}
    >
      {unlimited ? (
        <span className="inline-flex items-center gap-1.5">
          <InfinityIcon className="w-4 h-4" /> Unlimited today
        </span>
      ) : soldOut ? (
        <span className="inline-flex items-center gap-1.5" data-testid={`${testId}-soldout`}>
          <Clock className="w-4 h-4" /> All claimed — resets in {countdown}
        </span>
      ) : (
        <>
          <span className="inline-flex items-center gap-1.5" data-testid={`${testId}-count`}>
            <Flame className="w-4 h-4" /> {remaining.toLocaleString()} coupons left today
          </span>
          <span className="opacity-40">·</span>
          <span className="inline-flex items-center gap-1.5 font-mono tabular-nums" data-testid={`${testId}-countdown`}>
            <Clock className="w-3.5 h-3.5" /> {countdown}
          </span>
        </>
      )}
    </div>
  );
}

export default CouponScarcityStrip;
