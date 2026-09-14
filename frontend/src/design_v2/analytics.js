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
