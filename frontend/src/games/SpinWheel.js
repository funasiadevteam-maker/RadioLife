// Spin-wheel SVG. The server already decided the prize; this animation
// just provides theatre. We pick a "winning" sector index purely visual.
import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

export default function SpinWheel({ config, onSubmit, submitting, result, brand }) {
  const segments = config.segments || [];
  const [rotation, setRotation] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const wheelRef = useRef(null);
  const n = segments.length || 1;
  const sweep = 360 / n;

  useEffect(() => {
    // Triggered when result comes back
    if (result && !spinning) {
      setSpinning(true);
      // Land on a random sector — server result is the truth, this is theatre
      const land = Math.floor(Math.random() * n);
      const target = 360 * 5 + (360 - (land * sweep + sweep / 2));
      setRotation(target);
    }
  }, [result, n, sweep, spinning]);

  const onClick = () => {
    if (spinning || submitting || result) return;
    onSubmit({});
  };

  return (
    <div className="spin-wheel-shell" data-testid="spin-wheel">
      <div className="wheel-pointer" />
      <svg
        ref={wheelRef}
        viewBox="-110 -110 220 220"
        style={{ transform: `rotate(${rotation}deg)`,
                    transition: spinning ? `transform ${config.spin_duration_ms || 4000}ms cubic-bezier(.17,.67,.25,1)` : "none" }}>
        {segments.map((seg, i) => {
          const a1 = (i * sweep - 90) * Math.PI / 180;
          const a2 = ((i + 1) * sweep - 90) * Math.PI / 180;
          const r = 100;
          const x1 = Math.cos(a1) * r, y1 = Math.sin(a1) * r;
          const x2 = Math.cos(a2) * r, y2 = Math.sin(a2) * r;
          const large = sweep > 180 ? 1 : 0;
          const path = `M0,0 L${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2} Z`;
          const mid = ((i + 0.5) * sweep - 90) * Math.PI / 180;
          const tx = Math.cos(mid) * r * 0.6;
          const ty = Math.sin(mid) * r * 0.6;
          return (
            <g key={i}>
              <path d={path} fill={seg.color || "#444"} stroke="#0a0a0b" strokeWidth="1" />
              <text x={tx} y={ty} fill="#fff" fontSize="6"
                      textAnchor="middle" dominantBaseline="middle"
                      transform={`rotate(${(i + 0.5) * sweep + 90} ${tx} ${ty})`}
                      style={{ fontFamily: "Geist Mono, monospace", letterSpacing: "0.04em" }}>
                {(seg.label || "").slice(0, 14)}
              </text>
            </g>
          );
        })}
        <circle r="14" fill={brand || "#ff2d95"} stroke="#0a0a0b" strokeWidth="2" />
      </svg>
      <button
        className="spin-go-btn"
        onClick={onClick}
        disabled={submitting || spinning || result}
        data-testid="spin-go-btn">
        {submitting || spinning
          ? <><Loader2 size={14} className="spin" /> {result ? "Landing…" : "Spinning…"}</>
          : "Tap to spin"}
      </button>
    </div>
  );
}
