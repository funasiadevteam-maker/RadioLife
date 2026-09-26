// Owner Live Scheduler — a bar owner schedules a Live Shopping event and pins
// products right from their page. Creates a scheduled show then pins each
// product. POST /api/social/liveshows  +  POST /api/social/liveshows/{id}/products
import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { X, Plus, Trash2, Loader2, Radio, Calendar, ImagePlus, ShoppingBag, Sparkles } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const BACKEND = process.env.REACT_APP_BACKEND_URL || "";

const emptyProduct = () => ({ title: "", price: "", offer: "", image_url: "" });

export default function BarOwnerScheduler({ businessId, businessName, onClose, onScheduled }) {
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [when, setWhen] = useState("");
  const [cover, setCover] = useState("");
  const [catalog, setCatalog] = useState([]);
  const [products, setProducts] = useState([emptyProduct(), emptyProduct()]);
  const [busy, setBusy] = useState(false);
  const [genBusy, setGenBusy] = useState(false);

  const genCover = async () => {
    const prompt = (title.trim() || `${businessName || "bar"} live night`).slice(0, 180);
    setGenBusy(true);
    try {
      const { data } = await axios.post(`${API}/bar-games/cover-art`, { prompt }, { withCredentials: true });
      setCover(`${BACKEND}${data.url}`);
      toast.success("Cover art generated 🎨");
    } catch (e) {
      const code = e?.response?.data?.detail?.code;
      toast.error(code === "rate_limited" ? "Hourly art limit reached — try later." : "Couldn’t generate art. Paste a URL instead.");
    } finally { setGenBusy(false); }
  };

  useEffect(() => {
    axios.get(`${API}/shop/businesses/${businessId}/products`, { withCredentials: true })
      .then(({ data }) => setCatalog(data.products || []))
      .catch(() => setCatalog([]));
  }, [businessId]);

  const addFromCatalog = (c) => setProducts((l) => [
    ...l.filter((p) => p.title.trim()),
    { title: c.name || "", price: ((c.price_cents || 0) / 100).toString(), offer: "", image_url: c.image_url || "" },
  ]);

  const upd = (i, patch) => setProducts((l) => l.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const add = () => setProducts((l) => [...l, emptyProduct()]);
  const del = (i) => setProducts((l) => l.filter((_, j) => j !== i));

  const submit = async () => {
    if (title.trim().length < 2) { toast.info("Give your event a title."); return; }
    if (!when) { toast.info("Pick a date & time."); return; }
    setBusy(true);
    try {
      const { data: show } = await axios.post(`${API}/social/liveshows`,
        { title, description: desc, business_name: businessName || "",
          cover_url: cover.trim() || null,
          scheduled_at: new Date(when).toISOString() }, { withCredentials: true });
      const valid = products.filter((p) => p.title.trim());
      for (const p of valid) {
        await axios.post(`${API}/social/liveshows/${show.show_id}/products`,
          { title: p.title.trim(), price_cents: Math.round((parseFloat(p.price) || 0) * 100),
            offer: p.offer.trim(), image_url: p.image_url.trim() || null },
          { withCredentials: true });
      }
      toast.success(`Live event scheduled with ${valid.length} product${valid.length === 1 ? "" : "s"} 🗓️`);
      onScheduled?.();
      onClose?.();
    } catch (e) {
      toast.error("Couldn’t schedule the event.");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[100] grid place-items-center p-4 bg-black/70 backdrop-blur-sm"
         onClick={onClose} data-testid="bar-owner-scheduler">
      <div className="w-full max-w-md rounded-3xl border border-white/10 p-5 max-h-[90vh] overflow-auto"
           style={{ background: "linear-gradient(135deg,#160f2e,#241041)" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 text-white font-black text-lg"><Radio size={18} /> Schedule a Live event</div>
          <button onClick={onClose} className="text-slate-400" data-testid="scheduler-close"><X size={20} /></button>
        </div>

        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Event title (e.g. Friday Cocktail Night)" data-testid="scheduler-title"
               className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm text-white outline-none mb-3" />
        <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} placeholder="What’s the event about?" data-testid="scheduler-desc"
                  className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm text-white outline-none resize-none mb-3" />
        <label className="block text-xs text-slate-300 font-bold mb-1 flex items-center gap-1.5"><Calendar size={12} /> Date & time</label>
        <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} data-testid="scheduler-when"
               className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm text-slate-200 outline-none mb-4" />

        <label className="block text-xs text-slate-300 font-bold mb-1 flex items-center gap-1.5"><ImagePlus size={12} /> Cover image (optional)</label>
        {cover.trim() && <img src={cover} alt="" className="w-full h-28 object-cover rounded-xl mb-2 border border-white/10" />}
        <div className="flex gap-2 mb-4">
          <input value={cover} onChange={(e) => setCover(e.target.value)} placeholder="Paste image URL…" data-testid="scheduler-cover"
                 className="flex-1 min-w-0 rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm text-white outline-none" />
          <button onClick={genCover} disabled={genBusy} data-testid="scheduler-gen-cover"
                  className="shrink-0 px-3 rounded-xl font-black inline-flex items-center gap-1.5"
                  style={{ background: "rgba(168,85,247,0.25)", color: "#d8b4fe" }}>
            {genBusy ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />} AI
          </button>
        </div>

        {catalog.length > 0 && (
          <div className="mb-3" data-testid="scheduler-catalog">
            <div className="text-xs text-slate-300 font-bold mb-2 flex items-center gap-1.5"><ShoppingBag size={12} /> Add from your shop</div>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {catalog.map((c) => (
                <button key={c.product_id} onClick={() => addFromCatalog(c)} data-testid={`scheduler-catalog-${c.product_id}`}
                        className="shrink-0 w-24 text-left rounded-xl bg-white/[0.05] border border-white/10 overflow-hidden hover:border-pink-400/40">
                  {c.image_url ? <img src={c.image_url} alt="" className="w-full h-16 object-cover" /> : <div className="w-full h-16 bg-white/[0.06] grid place-items-center"><ShoppingBag size={16} className="text-slate-400" /></div>}
                  <div className="p-1.5">
                    <div className="text-[10px] font-bold text-white truncate">{c.name}</div>
                    <div className="text-[10px] text-emerald-300">{(c.price_cents / 100).toFixed(0)}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="text-xs text-slate-300 font-bold mb-2">Products to feature</div>
        <div className="space-y-2">
          {products.map((p, i) => (
            <div key={i} className="rounded-xl bg-white/[0.04] border border-white/10 p-2 space-y-2" data-testid={`scheduler-prod-${i}`}>
              <div className="flex items-center gap-2">
                <input value={p.title} onChange={(e) => upd(i, { title: e.target.value })} placeholder="Product name"
                       className="flex-1 min-w-0 rounded-lg bg-white/[0.06] px-2 py-2 text-sm text-white outline-none" />
                <button onClick={() => del(i)} className="text-slate-400 p-1"><Trash2 size={15} /></button>
              </div>
              <div className="flex items-center gap-2">
                <input value={p.price} onChange={(e) => upd(i, { price: e.target.value })} inputMode="decimal" placeholder="Price"
                       className="w-20 rounded-lg bg-white/[0.06] px-2 py-2 text-sm text-white outline-none" />
                <input value={p.offer} onChange={(e) => upd(i, { offer: e.target.value })} placeholder="Offer (e.g. -20%)"
                       className="flex-1 min-w-0 rounded-lg bg-white/[0.06] px-2 py-2 text-sm text-white outline-none" />
              </div>
              <input value={p.image_url} onChange={(e) => upd(i, { image_url: e.target.value })} placeholder="Image URL (optional)"
                     className="w-full rounded-lg bg-white/[0.06] px-2 py-2 text-xs text-white outline-none" />
            </div>
          ))}
        </div>
        <button onClick={add} data-testid="scheduler-add-prod"
                className="mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-white h-9 px-3 rounded-full bg-white/10">
          <Plus size={13} /> Add product
        </button>

        <button onClick={submit} disabled={busy} data-testid="scheduler-submit"
                className="mt-4 w-full h-11 rounded-full text-white font-black inline-flex items-center justify-center gap-2"
                style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Radio size={16} />} Schedule event
        </button>
      </div>
    </div>
  );
}
