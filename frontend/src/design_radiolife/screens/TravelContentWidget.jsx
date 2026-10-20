// Generic Travelpayouts "content" widget (Klook hotels, car rental, etc.).
// These are async DOM scripts that inject an iframe after themselves, so we
// mount the <script> inside a dedicated container. Web only — mobile renders
// the same scripts inside a WebView (app/shop/travel/search.tsx).
import { useEffect, useRef, useState } from "react";

export default function TravelContentWidget({ src, minHeight = 360 }) {
  const ref = useRef(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.innerHTML = "";
    setReady(false);
    const s = document.createElement("script");
    s.async = true;
    s.charset = "utf-8";
    s.src = src;
    s.onload = () => setReady(true);
    s.onerror = () => setReady(true);
    el.appendChild(s);
    return () => { el.innerHTML = ""; };
  }, [src]);

  return (
    <div data-testid="travel-content-widget" style={{ width: "100%" }}>
      <div ref={ref} style={{ minHeight }} />
      {!ready && (
        <div className="text-sm fz-muted text-center py-6" data-testid="travel-content-loading">
          Loading live deals…
        </div>
      )}
    </div>
  );
}
