// FUUSIC — lightweight dependency-free confetti burst.
// Celebrates the first time a member's post lands on their own wall.
const COLORS = ["#a855f7", "#ec4899", "#22c55e", "#f59e0b", "#38bdf8", "#f43f5e"];

export function fireConfetti(count = 70) {
  if (typeof document === "undefined") return;
  const root = document.createElement("div");
  root.setAttribute("data-testid", "fuusic-confetti");
  Object.assign(root.style, {
    position: "fixed", inset: "0", pointerEvents: "none", zIndex: "2147483000",
    overflow: "hidden",
  });
  document.body.appendChild(root);

  const cx = window.innerWidth / 2;
  const cy = window.innerHeight * 0.4;

  for (let i = 0; i < count; i++) {
    const p = document.createElement("div");
    const size = 6 + Math.random() * 8;
    const color = COLORS[i % COLORS.length];
    const round = Math.random() > 0.5;
    Object.assign(p.style, {
      position: "absolute", left: `${cx}px`, top: `${cy}px`,
      width: `${size}px`, height: `${size * (round ? 1 : 0.45)}px`,
      background: color, borderRadius: round ? "999px" : "2px",
      opacity: "1",
    });
    root.appendChild(p);

    const angle = Math.random() * Math.PI * 2;
    const velocity = 120 + Math.random() * 260;
    const dx = Math.cos(angle) * velocity;
    const dy = Math.sin(angle) * velocity - (120 + Math.random() * 160);
    const rot = (Math.random() * 720 - 360);
    const dur = 1100 + Math.random() * 900;

    p.animate(
      [
        { transform: "translate(0,0) rotate(0deg)", opacity: 1 },
        { transform: `translate(${dx}px, ${dy}px) rotate(${rot / 2}deg)`, opacity: 1, offset: 0.4 },
        { transform: `translate(${dx * 1.2}px, ${dy + 420}px) rotate(${rot}deg)`, opacity: 0 },
      ],
      { duration: dur, easing: "cubic-bezier(.2,.6,.3,1)", fill: "forwards" }
    );
  }
  setTimeout(() => root.remove(), 2200);
}

export default fireConfetti;
