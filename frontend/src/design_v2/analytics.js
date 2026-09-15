// New Look V2 analytics — thin wrapper over the existing home-events ingest.
import axios from "axios";
import { API } from "@/AuthContext";

export function fireV2Event(event, extra = {}) {
  try {
    axios.post(
      `${API}/shell/home-events`,
      { event, surface: "web", variant: "new_look_v2", ...extra },
      { withCredentials: true },
    ).catch(() => {});
  } catch (_e) { /* noop */ }
}

export const HERO_IMG =
  "https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/1ee6291ca7eb9d48ba117827e3fd4ec87fbbd39684264d37717ffd7d930f9db3.jpeg";

// Live Hero Vibe — image + copy shift with the time of day. The listener's
// top genre is woven into the sub-copy + a tag chip at render time.
export const HERO_VIBES = {
  morning: {
    img: "https://images.unsplash.com/photo-1510133744874-096621a0e01e?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    kicker: "Fresh start",
    h1: "Rise &",
    h2: "shine",
    script: "Mornings, your way",
    slotLabel: "your morning",
    lines: ["Your music.", "Your morning.", "Your energy."],
  },
  afternoon: {
    img: "https://images.unsplash.com/photo-1761301643797-6f147de68761?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    kicker: "Today's vibe",
    h1: "Ready to",
    h2: "listen?",
    script: "Music Connects Us",
    slotLabel: "your afternoon",
    lines: ["Your music.", "Your mood.", "A better you."],
  },
  evening: {
    img: "https://images.unsplash.com/photo-1611244806964-91d204d4a2a7?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    kicker: "Golden hour",
    h1: "Unwind",
    h2: "tonight",
    script: "Sundown sessions",
    slotLabel: "your evening",
    lines: ["Your music.", "Your evening.", "Your escape."],
  },
  night: {
    img: "https://images.unsplash.com/photo-1540039155733-5bb30b53aa14?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    kicker: "After dark",
    h1: "Late night",
    h2: "sessions",
    script: "Turn it up",
    slotLabel: "late nights",
    lines: ["Your music.", "Your night.", "No skips missed."],
  },
};

export function heroSlot(d = new Date()) {
  const h = d.getHours();
  if (h >= 5 && h < 12) return "morning";
  if (h >= 12 && h < 17) return "afternoon";
  if (h >= 17 && h < 22) return "evening";
  return "night";
}
