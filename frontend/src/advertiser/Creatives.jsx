// Phase 18a — Creative library.
import { useEffect, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { Check, AlertTriangle, X, Sparkles } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Creatives({ advertiserId }) {
  const [items, setItems] = useState([]);
  useEffect(() => {
    if (!advertiserId) return;
    axios.get(`${API}/advertiser/${advertiserId}/creatives`)
            .then((r) => setItems(r.data.items || []))
            .catch(() => {});
  }, [advertiserId]);
  return (
    <div className="space-y-4" data-testid="advertiser-creatives">
      <div className="flex items-center justify-between">
        <h2 className="font-display font-bold text-2xl">Creative library</h2>
        <Link to="/advertiser/creatives/ai" data-testid="creatives-ai-cta"
                  className="inline-flex items-center gap-2 rounded-xl px-3 py-2
                                  bg-amber-400 text-bg-base font-display font-bold text-sm
                                  hover:bg-amber-300">
          <Sparkles size={14} /> Generate with AI
        </Link>
      </div>
      {items.length === 0 ? (
        <p className="text-text-secondary text-sm">No creatives yet.  Upload via the campaign wizard.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map((cr) => {
            const v = cr.brand_safety_check?.verdict;
            const tone = v === "approved" ? "#4ade80" : v === "rejected" ? "#fb7185" : "#fdb756";
            const Ico = v === "approved" ? Check : v === "rejected" ? X : AlertTriangle;
            return (
              <div key={cr.id} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
                <div className="flex items-center gap-2">
                  <Ico size={14} style={{color: tone}} />
                  <div className="text-sm font-display font-bold truncate flex-1">{cr.title}</div>
                </div>
                <div className="text-[10px] uppercase tracking-widest font-mono mt-1" style={{color: tone}}>
                  {v || cr.status}
                </div>
                {cr.audio_url && (
                  <audio src={`${process.env.REACT_APP_BACKEND_URL}${cr.audio_url}`} controls className="w-full mt-2 h-8" />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
