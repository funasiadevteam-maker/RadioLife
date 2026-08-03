// Phase 15a — desktop keyboard shortcuts. Mounted once at <AppShell> for
// in-shell routes only; bare routes (login / admin / advertiser / etc.)
// pass `enabled: false` and the listener never attaches.
//
// Event contract (window events) — observable from tests + 15b consumers:
//   bigfm:shortcut:focus-search   ←   /
//   bigfm:player:toggle           ←   space
//   bigfm:player:volup            ←   →
//   bigfm:player:voldown          ←   ←
//   bigfm:list:next               ←   j
//   bigfm:list:prev               ←   k
//   bigfm:route:home|radio|play|trivia|wallet|games|map  ← g + key
//
// For `/` we ALSO focus `[data-shortcut-target="search"]` if present
// (the topbar search input). The event still fires either way so tests
// can observe a single signal regardless of whether a focus target exists.
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

const ROUTES = {
  h: { path: "/",          ev: "home" },
  r: { path: "/radio",     ev: "radio" },
  p: { path: "/play",      ev: "play" },
  t: { path: "/trivia",    ev: "trivia" },
  w: { path: "/wallet",    ev: "wallet" },
  g: { path: "/passport",  ev: "games" }, // "g g" = passport/games hub
  m: { path: "/map",       ev: "map" },
};

function fire(name, detail) {
  try {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  } catch (_) { /* old browsers */ }
}

export function useKeyboardShortcuts({ enabled = true } = {}) {
  const navigate = useNavigate();
  const gMode = useRef(false);
  const gTimer = useRef(null);

  useEffect(() => {
    if (!enabled) return undefined;

    const isTyping = (t) => {
      if (!t) return false;
      const tag = t.tagName || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
      if (t.isContentEditable) return true;
      return false;
    };

    const onKey = (e) => {
      // Modifier keys reserved for the browser/OS.
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const typing = isTyping(e.target);

      // Two-stroke "g X" routing.
      if (gMode.current) {
        gMode.current = false;
        if (gTimer.current) { clearTimeout(gTimer.current); gTimer.current = null; }
        const k = (e.key || "").toLowerCase();
        const dest = ROUTES[k];
        if (dest) {
          e.preventDefault();
          fire(`bigfm:route:${dest.ev}`, { path: dest.path });
          navigate(dest.path);
        }
        return;
      }

      // While typing in a field we ONLY allow Escape (and we still let `/`
      // pass through so the next focus on body can trigger it, but here
      // we just bail — fields handle their own input).
      if (typing) return;

      // `g` enters two-stroke mode.
      if (e.key === "g" || e.key === "G") {
        gMode.current = true;
        if (gTimer.current) clearTimeout(gTimer.current);
        gTimer.current = setTimeout(() => { gMode.current = false; }, 1200);
        return;
      }

      switch (e.key) {
        case "/": {
          e.preventDefault();
          fire("bigfm:shortcut:focus-search");
          const el = document.querySelector('[data-shortcut-target="search"]');
          if (el && typeof el.focus === "function") {
            try { el.focus({ preventScroll: false }); }
            catch (_) { el.focus(); }
            if (typeof el.select === "function") {
              try { el.select(); } catch (_) { /* noop */ }
            }
          }
          break;
        }
        case " ":
          e.preventDefault();
          fire("bigfm:player:toggle");
          break;
        case "ArrowRight":
          fire("bigfm:player:volup");
          break;
        case "ArrowLeft":
          fire("bigfm:player:voldown");
          break;
        case "j": case "J":
          fire("bigfm:list:next");
          break;
        case "k": case "K":
          fire("bigfm:list:prev");
          break;
        default:
          break;
      }
    };

    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (gTimer.current) clearTimeout(gTimer.current);
    };
  }, [enabled, navigate]);
}
