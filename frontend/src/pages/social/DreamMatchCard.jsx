// Public, no-login view of a shared Dream Compatibility card.
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { Loader2, Heart, Sparkles, Download, Share2 } from "lucide-react";

const B = process.env.REACT_APP_BACKEND_URL || "";

export default function DreamMatchCard() {
  const { cardId } = useParams();
  const navigate = useNavigate();
  const [c, setC] = useState(null);
  const [err, setErr] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    axios.get(`${B}/api/social/compatibility/card/${cardId}`)
      .then(({ data }) => setC(data)).catch(() => setErr(true));
  }, [cardId]);

  // Best-effort OG/Twitter meta for in-app browsers (crawlers use the SSR route).
  useEffect(() => {
    if (!c) return;
    const img = c.image_url || `${B}/api/social/compatibility/card/${cardId}/image.png`;
    const title = `${c.owner_name} & ${c.target_name} — ${c.score}% dream match ✨`;
    document.title = title;
    const set = (attr, key, val) => {
      let el = document.head.querySelector(`meta[${attr}="${key}"]`);
      if (!el) { el = document.createElement("meta"); el.setAttribute(attr, key); document.head.appendChild(el); }
      el.setAttribute("content", val);
    };
    set("property", "og:title", title);
    set("property", "og:image", img);
    set("name", "twitter:card", "summary_large_image");
    set("name", "twitter:image", img);
  }, [c, cardId]);

  const imageUrl = c?.image_url || `${B}/api/social/compatibility/card/${cardId}/image.png`;
  const shareUrl = `${B}/api/social/dreams/match/${cardId}`;

  const download = async () => {
    setBusy(true);
    try {
      const res = await fetch(imageUrl);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `dream-match-${cardId}.png`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (_) {} finally { setBusy(false); }
  };

  const share = async () => {
    const payload = { title: "Our dream match ✨", text: `${c.owner_name} & ${c.target_name} — ${c.score}% dream match`, url: shareUrl };
    if (navigator.share) { try { await navigator.share(payload); return; } catch (_) {} }
    try { await navigator.clipboard.writeText(shareUrl); } catch (_) {}
  };

  if (err) return (
    <div className="min-h-screen grid place-items-center bg-[#0d0a24] text-white" data-testid="match-card-missing">
      <div className="text-center">
        <p className="text-lg font-bold">This match card isn’t available.</p>
        <button onClick={() => navigate("/social/dreams")} className="mt-4 px-5 h-11 rounded-full font-bold" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>Explore Dreams</button>
      </div>
    </div>
  );
  if (!c) return <div className="min-h-screen grid place-items-center bg-[#0d0a24]"><Loader2 className="animate-spin text-violet-400" /></div>;

  return (
    <div className="min-h-screen flex items-center justify-center p-5" style={{ background: "radial-gradient(1200px 600px at 50% -10%, #4c1d95 0%, #0d0a24 60%)" }} data-testid="match-card-public">
      <div className="w-full max-w-md">
        {/* Share-ready Match Card Art */}
        <img src={imageUrl} alt={`${c.owner_name} & ${c.target_name} dream match`} data-testid="match-card-art"
             className="w-full rounded-[24px] border border-rose-400/25 shadow-2xl mb-4"
             style={{ aspectRatio: "1200 / 630", objectFit: "cover", background: "#1e1b4b" }} />

        <div className="rounded-[28px] p-7 text-center border border-rose-400/25" style={{ background: "linear-gradient(160deg,#2e1065,#4c1d95 55%,#be185d)" }}>
          <div className="inline-flex items-center gap-1.5 text-[10px] font-bold text-amber-200/90 uppercase tracking-widest"><Sparkles size={12} /> {c.label}</div>
          <div className="flex items-center justify-center gap-3 mt-4 mb-1 text-white">
            <span className="font-black">{c.owner_name}</span>
            <Heart size={20} className="text-rose-300 fill-rose-400" />
            <span className="font-black">{c.target_name}</span>
          </div>
          <div className="text-7xl font-black text-white my-2">{c.score}%</div>
          <div className="text-xl font-black text-white">{c.headline}</div>
          <p className="text-sm text-rose-100/90 mt-3 leading-relaxed">{c.blurb}</p>
          {c.shared_themes?.length > 0 && (
            <div className="flex gap-2 flex-wrap justify-center mt-4">
              {c.shared_themes.map((t, i) => <span key={i} className="text-[11px] px-3 py-1 rounded-full bg-white/[0.12] text-white">{t}</span>)}
            </div>
          )}
          <p className="text-[12px] text-rose-100/70 mt-4">{c.shared_note}</p>
          {(c.my_sign || c.their_sign) && (
            <p className="text-[11px] text-violet-200/70 mt-2">{[c.my_sign, c.their_sign].filter(Boolean).join(" · ")}</p>
          )}

          <div className="flex gap-2 mt-6">
            <button onClick={download} disabled={busy} data-testid="match-card-download"
                    className="flex-1 h-12 rounded-full font-black text-white inline-flex items-center justify-center gap-2 bg-white/[0.16]">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />} Download
            </button>
            <button onClick={share} data-testid="match-card-share"
                    className="flex-1 h-12 rounded-full font-black text-white inline-flex items-center justify-center gap-2" style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>
              <Share2 size={16} /> Share
            </button>
          </div>

          <button onClick={() => navigate("/social/dreams")} data-testid="match-card-cta"
                  className="mt-3 w-full h-11 rounded-full font-bold text-white/90 bg-white/[0.08]">
            Find your own dream match ✨
          </button>
          <p className="text-[10px] text-violet-200/50 mt-3">{c.disclaimer}</p>
        </div>
      </div>
    </div>
  );
}
