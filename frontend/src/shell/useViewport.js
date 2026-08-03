// Phase 15a — viewport hook. SSR-safe.
import { useEffect, useState } from "react";

export const BREAKPOINTS = { sm: 640, md: 768, lg: 1024, xl: 1280 };

export function useViewport() {
  const get = () => {
    if (typeof window === "undefined") {
      return { w: 1280, h: 800, layout: "desktop" };
    }
    const w = window.innerWidth;
    const h = window.innerHeight;
    const layout =
      w >= BREAKPOINTS.lg ? "desktop" :
      w >= BREAKPOINTS.md ? "tablet"  : "mobile";
    return { w, h, layout };
  };
  const [vp, setVp] = useState(get);
  useEffect(() => {
    const on = () => setVp(get());
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return vp;
}
