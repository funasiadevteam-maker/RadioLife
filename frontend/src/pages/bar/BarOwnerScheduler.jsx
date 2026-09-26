// Owner Live Scheduler — a bar owner schedules a Live Shopping event and pins
// products right from their page. Creates a scheduled show then pins each
// product. POST /api/social/liveshows  +  POST /api/social/liveshows/{id}/products
import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { X, Plus, Trash2, Loader2, Radio, Calendar } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const emptyProduct = () => ({ title: "", price: "", offer: "", image_url: "" });

export default function BarOwnerScheduler({ businessId, businessName, onClose, onScheduled }) {
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [when, setWhen] = useState("");
  const [products, setProducts] = useState([emptyProduct(), emptyProduct()]);
  const [busy, setBusy] = useState(false);

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
