// FUUSIC — public, no-login view of a shared FUUSIC Live highlight clip.
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Loader2, ShoppingBag, Share2, Radio } from "lucide-react";

const B = process.env.REACT_APP_BACKEND_URL || "";
const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

export default function SocialClip() {
  const { clipId } = useParams();
  const [clip, setClip] = useState(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    axios.get(`${B}/api/social/liveshows/clips/${clipId}`)
      .then(({ data }) => {
        setClip(data);
        document.title = `${data.title} — FUUSIC Live`;
      })
      .catch(() => setErr(true));
  }, [clipId]);

  const share = async () => {
    const url = `${B}/api/social/liveshows/clips/${clipId}/share`;
    try {
      if (navigator.share) await navigator.share({ title: clip.title, text: clip.caption, url });
      else await navigator.clipboard.writeText(url);
    } catch (_) {}
  };

  if (err) return <Center>Clip not found.</Center>;
  if (!clip) return <Center><Loader2 className="animate-spin" /></Center>;

  return (
    <div className="min-h-screen bg-[#0b0a1a] text-white flex items-center justify-center p-5">
      <div className="w-full max-w-lg" data-testid="public-clip">
        <div className="flex items-center gap-2 mb-4 justify-center">
          <span className="w-8 h-8 rounded-xl grid place-items-center" style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}><Radio size={16} /></span>
          <span className="font-black tracking-tight text-lg" style={{ background: "linear-gradient(90deg,#a855f7,#ec4899,#3b82f6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>FUUSIC</span>
        </div>
        <img src={clip.image_url} alt={clip.title} data-testid="public-clip-art"
             className="w-full rounded-3xl border border-white/10 shadow-2xl" style={{ aspectRatio: "1200 / 630", objectFit: "cover" }} />
        <h1 className="mt-5 text-2xl font-black">{clip.title}</h1>
        {clip.caption && <p className="mt-1 text-violet-100/80">{clip.caption}</p>}
        {clip.business_name && <p className="mt-1 text-xs text-violet-300/70">by {clip.business_name}</p>}

        {clip.products?.length > 0 && (
          <div className="mt-5 space-y-2" data-testid="public-clip-products">
            <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wide">Shop this clip</div>
            {clip.products.map((p) => (
              <div key={p.product_id} className="flex items-center gap-3 rounded-2xl bg-white/[0.04] border border-white/10 px-4 py-3">
                <div className="flex-1 min-w-0"><div className="text-sm font-bold truncate">{p.title}</div>{p.offer && <div className="text-[11px] text-rose-300">{p.offer}</div>}</div>
                <div className="text-sm font-black">{money(p.price_cents)}</div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-6 flex gap-3">
          <a href={`${B}/`} data-testid="public-clip-cta" className="flex-1 h-12 rounded-full font-black text-white inline-flex items-center justify-center gap-2" style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
            <ShoppingBag size={16} /> Watch &amp; shop on FUUSIC
          </a>
          <button onClick={share} data-testid="public-clip-share" className="h-12 px-5 rounded-full font-bold text-white inline-flex items-center justify-center gap-2 bg-white/[0.1]">
            <Share2 size={16} />
          </button>
        </div>
        <p className="text-[10px] text-violet-200/50 mt-4 text-center">Everything You Love, Together.</p>
      </div>
    </div>
  );
}

function Center({ children }) {
  return <div className="min-h-screen bg-[#0b0a1a] text-white flex items-center justify-center">{children}</div>;
}
