// Travelpayouts White Label — live flight/hotel metasearch (browser/DOM widget).
// Loads the WL module script ONCE, renders stable #tpwl-search + #tpwl-tickets
// mounts on the same page (search + results together). Web only — the mobile
// app renders the same widget inside a WebView (app/shop/travel/search.tsx).
import { useEffect } from "react";

const WL_ID = "23601";
const WL_SRC = `https://tpwidg.com/wl_web/main.js?wl_id=${WL_ID}`;

function loadTravelpayoutsOnce() {
  if (window.__tpwlLoadPromise) return window.__tpwlLoadPromise;
  // Configuration must be set before the module script executes.
  window.TPWL_CONFIGURATION = {
    ...(window.TPWL_CONFIGURATION || {}),
    resultsURL: `${window.location.origin}/shop/travel`,
    sub_id: "fuusic_app",
  };
  if (document.querySelector(`script[data-tpwl-main="${WL_ID}"]`)) {
    window.__tpwlLoadPromise = Promise.resolve();
    return window.__tpwlLoadPromise;
  }
  window.__tpwlLoadPromise = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.type = "module";
    s.async = true;
    s.src = WL_SRC;
    s.dataset.tpwlMain = WL_ID;
    s.onload = resolve;
    s.onerror = () => reject(new Error("tpwl_load_failed"));
    document.head.appendChild(s);
  });
  return window.__tpwlLoadPromise;
}

export default function TravelWidget() {
  useEffect(() => {
    let cancelled = false;
    if (document.getElementById("tpwl-search") && document.getElementById("tpwl-tickets")) {
      loadTravelpayoutsOnce().catch((e) => {
        if (!cancelled) console.error("Travelpayouts widget:", e.message);
      });
    }
    return () => { cancelled = true; };
  }, []);

  return (
    <div data-testid="tpwl-widget" style={{ width: "100%" }}>
      <div id="tpwl-search" />
      <div id="tpwl-tickets" style={{ marginTop: 12 }} />
    </div>
  );
}
