// Mystery box: user picks one of N boxes, reveal animation, server tells truth.
import { useState } from "react";
import { Loader2 } from "lucide-react";

export default function MysteryBox({ config, onSubmit, submitting, result, brand }) {
  const boxes = (config.boxes && config.boxes.length ? config.boxes
                       : Array.from({ length: config.num_boxes || 3 },
                                    (_, i) => ({ label: `Box ${i + 1}` })));
  const [chosen, setChosen] = useState(null);

  const pick = (i) => {
    if (chosen !== null || submitting || result) return;
    setChosen(i);
    onSubmit({ box_idx: i });
  };

  return (
    <div className="mystery-shell" data-testid="mystery-box">
      <h2 className="mystery-instruct">Pick one to reveal your prize</h2>
      <div className="mystery-grid"
              style={{ "--n": Math.min(boxes.length, 5) }}>
        {boxes.map((b, i) => (
          <button
            key={i}
            className={`mystery-box ${chosen === i ? "chosen" : ""} ${chosen !== null && chosen !== i ? "dimmed" : ""}`}
            onClick={() => pick(i)}
            disabled={submitting || result}
            data-testid={`mystery-box-${i}`}
            style={{ "--brand": brand || "#ff2d95" }}>
            <div className="mystery-front">
              <span className="mystery-q">?</span>
              <div className="mystery-label mono">{b.label}</div>
            </div>
          </button>
        ))}
      </div>
      {chosen !== null && submitting && (
        <div className="mystery-hint mono">
          <Loader2 size={12} className="spin" /> Opening Box {chosen + 1}…
        </div>
      )}
    </div>
  );
}
