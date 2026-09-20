// FUUSIC Social V2 — Phase 3 web: FUUSIC LIVE (livestream commerce).
// Video transport is LiveKit (client SDK not bundled → the stage shows a live
// placeholder); the commerce, pinned products, live checkout and chat are fully
// interactive on the shared /api/social/liveshows contract.
import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2, Video, Radio, X, Send, ShoppingBag, Plus, Tag, Users,
  Trash2, StopCircle, Sparkles, Scissors, UserPlus,
} from "lucide-react";
import { Avatar } from "./SocialV2";

const B = process.env.REACT_APP_BACKEND_URL || "";
const api = axios.create({ baseURL: `${B}/api/social/liveshows`, withCredentials: true });
const grad = { background: "linear-gradient(135deg,#a855f7,#ec4899)" };
const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

export function LiveTab() {
  const [shows, setShows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(null);       // show_id being viewed
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try { const { data } = await api.get("?status=live"); setShows(data.items || []); }
    catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (open) return <LiveViewer showId={open} onClose={() => { setOpen(null); load(); }} />;

  return (
    <div className="space-y-4" data-testid="social-live">
      <button onClick={() => setCreating(true)} data-testid="live-golive"
              className="w-full rounded-3xl p-5 flex items-center gap-4 border border-white/10 text-left"
              style={{ background: "linear-gradient(120deg,#3a0f52,#7f1d4a)" }}>
        <span className="grid place-items-center w-14 h-14 rounded-2xl text-white shrink-0" style={grad}><Video size={24} /></span>
        <div className="flex-1"><div className="text-lg font-black">Go Live</div>
          <div className="text-sm text-white/70">Stream to your fans and sell your products live</div></div>
        <span className="text-xs font-black px-3 py-1.5 rounded-full bg-red-500/30 text-red-200">● LIVE</span>
      </button>

      {loading ? <div className="flex justify-center py-16"><Loader2 className="animate-spin text-purple-400" /></div>
        : shows.length === 0 ? (
          <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-8 text-center text-slate-400">
            No live shows right now — tap <b>Go Live</b> to start one. 🎥
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 gap-3">
            {shows.map((s) => (
              <button key={s.show_id} onClick={() => setOpen(s.show_id)} data-testid={`live-show-${s.show_id}`}
                      className="text-left rounded-2xl overflow-hidden bg-white/[0.04] border border-white/10 hover:border-pink-400/40">
                <div className="h-32 relative grid place-items-center" style={{ background: "linear-gradient(135deg,#4c1d95,#be185d)" }}>
                  {s.cover_url ? <img src={s.cover_url} alt="" className="w-full h-full object-cover" /> : <Radio className="text-white/60" size={30} />}
                  <span className="absolute top-2 left-2 text-[10px] font-black px-2 py-0.5 rounded-full bg-red-500/80 text-white flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" /> LIVE</span>
                  <span className="absolute top-2 right-2 text-[10px] font-black px-2 py-0.5 rounded-full bg-black/50 text-white flex items-center gap-1"><Users size={11} /> {s.viewer_count}</span>
                </div>
                <div className="p-3">
                  <div className="text-sm font-black truncate">{s.title}</div>
                  <div className="text-[11px] text-slate-400 truncate">{s.business_name} · {s.pinned_products?.length || 0} products</div>
                </div>
              </button>
            ))}
          </div>
        )}
      {creating && <GoLiveModal onClose={() => setCreating(false)} onLive={(id) => { setCreating(false); setOpen(id); }} />}
    </div>
  );
}

function GoLiveModal({ onClose, onLive }) {
  const [title, setTitle] = useState("");
  const [biz, setBiz] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    if (title.trim().length < 2) { toast.info("Give your show a title."); return; }
    setBusy(true);
    try { const { data } = await api.post("", { title, business_name: biz, description: desc }); toast.success("You’re live! 🔴"); onLive(data.show_id); }
    catch (_) { toast.error("Couldn’t start the show."); } finally { setBusy(false); }
  };
  return (
    <Modal title="Go Live" onClose={onClose} testid="golive-modal">
      <div className="space-y-3">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Show title" data-testid="golive-title"
               className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        <input value={biz} onChange={(e) => setBiz(e.target.value)} placeholder="Business name (optional)" data-testid="golive-biz"
               className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} placeholder="What are you showing today?" data-testid="golive-desc"
                  className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none resize-none" />
        <button onClick={go} disabled={busy} data-testid="golive-start"
                className="w-full h-11 rounded-full text-white font-black inline-flex items-center justify-center gap-2" style={grad}>
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Video size={16} />} Start streaming
        </button>
      </div>
    </Modal>
  );
}

function LiveViewer({ showId, onClose }) {
  const [show, setShow] = useState(null);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [pinOpen, setPinOpen] = useState(false);
  const [buying, setBuying] = useState(null);
  const [clips, setClips] = useState([]);
  const [savingClip, setSavingClip] = useState(false);
  const [cohostOpen, setCohostOpen] = useState(false);
  const lastTs = useRef(null);
  const chatEnd = useRef(null);

  const loadShow = useCallback(async () => {
    try { const { data } = await api.get(`/${showId}`); setShow(data); } catch (_) { onClose(); }
  }, [showId, onClose]);
  const loadClips = useCallback(async () => {
    try { const { data } = await api.get(`/${showId}/clips`); setClips(data.items || []); } catch (_) {}
  }, [showId]);

  useEffect(() => { loadShow(); loadClips(); }, [loadShow, loadClips]);

  // Poll chat + heartbeat every 3s.
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      if (stop) return;
      try {
        const q = lastTs.current ? `?after=${encodeURIComponent(lastTs.current)}` : "";
        const { data } = await api.get(`/${showId}/messages${q}`);
        if (data.items?.length) {
          setMessages((m) => {
            const have = new Set(m.map((x) => x.id));
            const add = data.items.filter((x) => !have.has(x.id));
            return add.length ? [...m, ...add] : m;
          });
          lastTs.current = data.items[data.items.length - 1].created_at;
        }
        const { data: hb } = await api.post(`/${showId}/heartbeat`);
        setShow((s) => s ? { ...s, viewer_count: hb.viewer_count } : s);
      } catch (_) {}
    };
    const iv = setInterval(tick, 3000); tick();
    return () => { stop = true; clearInterval(iv); };
  }, [showId]);

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async () => {
    if (!text.trim()) return;
    const t = text.trim(); setText("");
    try { const { data } = await api.post(`/${showId}/messages`, { text: t });
      setMessages((m) => [...m, data]); lastTs.current = data.created_at; } catch (_) {}
  };
  const buy = async (p) => {
    setBuying(p.product_id);
    try {
      const { data } = await api.post(`/${showId}/checkout`, { product_id: p.product_id, origin_url: window.location.origin });
      if (data.checkout_url) window.location.href = data.checkout_url;
      else toast.success("Added — it’s free! 🎁");
    } catch (_) { toast.error("Couldn’t start checkout."); } finally { setBuying(null); }
  };
  const endShow = async () => { try { await api.post(`/${showId}/end`); toast.success("Show ended"); onClose(); } catch (_) {} };
  const unpin = async (pid) => { try { await api.delete(`/${showId}/products/${pid}`); loadShow(); } catch (_) {} };
  const saveHighlight = async () => {
    setSavingClip(true);
    try { await api.post(`/${showId}/clips`, { note: "" }); await loadClips(); toast.success("Highlight clip saved ✨"); }
    catch (_) { toast.error("Couldn’t save the clip."); } finally { setSavingClip(false); }
  };
  const buyClip = async (clip, p) => {
    setBuying(p.product_id);
    try {
      const { data } = await api.post(`/clips/${clip.clip_id}/checkout`, { product_id: p.product_id, origin_url: window.location.origin });
      if (data.checkout_url) window.location.href = data.checkout_url;
      else toast.success("Added — it’s free! 🎁");
    } catch (_) { toast.error("Couldn’t start checkout."); } finally { setBuying(null); }
  };

  if (!show) return <div className="flex justify-center py-20"><Loader2 className="animate-spin text-purple-400" /></div>;

  return (
    <div data-testid="live-viewer">
      <button onClick={onClose} data-testid="live-back" className="mb-3 inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white"><X size={16} /> Back to Live</button>
      {/* Stage */}
      <div className="relative rounded-3xl overflow-hidden border border-pink-400/25 aspect-video grid place-items-center"
           style={{ background: "radial-gradient(800px 400px at 50% 0%,#4c1d95,#0d0a24 70%)" }}>
        <div className="text-center">
          <div className="inline-flex items-center gap-1.5 text-[11px] font-black px-3 py-1 rounded-full bg-red-500/80 text-white mb-3"><span className="w-2 h-2 rounded-full bg-white animate-pulse" /> LIVE</div>
          <Avatar name={show.host?.name} url={show.host?.avatar_url} size={72} />
          <div className="mt-3 text-lg font-black">{show.business_name}</div>
          <div className="text-sm text-slate-300">{show.title}</div>
          <div className="mt-2 text-[11px] text-slate-400">{show.mode === "live" ? "Live video stream" : "Simulated stream (preview)"} · <Users size={11} className="inline" /> {show.viewer_count} watching</div>
        </div>
        {show.can_manage && (
          <div className="absolute top-3 right-3 flex flex-wrap gap-2 justify-end max-w-[70%]">
            <button onClick={() => setPinOpen(true)} data-testid="live-pin-open" className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-white text-xs font-black" style={grad}><Plus size={14} /> Pin</button>
            <button onClick={saveHighlight} disabled={savingClip} data-testid="live-clip" className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-white/15 text-white text-xs font-black">{savingClip ? <Loader2 size={14} className="animate-spin" /> : <Scissors size={14} />} Highlight</button>
            {show.is_host && <button onClick={() => setCohostOpen(true)} data-testid="live-cohost-open" className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-white/15 text-white text-xs font-black"><UserPlus size={14} /> Co-host</button>}
            {show.is_host && <button onClick={endShow} data-testid="live-end" className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full bg-red-500/80 text-white text-xs font-black"><StopCircle size={14} /> End</button>}
          </div>
        )}
      </div>

      {/* Pinned products */}
      <div className="mt-4">
        <div className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2 flex items-center gap-1.5"><ShoppingBag size={13} /> Shop this show</div>
        {(!show.pinned_products || show.pinned_products.length === 0) ? (
          <div className="text-sm text-slate-500">{show.is_host ? "Pin a product to sell it live." : "No products pinned yet."}</div>
        ) : (
          <div className="flex gap-3 overflow-x-auto no-scrollbar pb-1" data-testid="live-products">
            {show.pinned_products.map((p) => (
              <div key={p.product_id} className="flex-shrink-0 w-52 rounded-2xl bg-white/[0.04] border border-white/10 overflow-hidden" data-testid={`live-product-${p.product_id}`}>
                <div className="h-28 grid place-items-center bg-purple-500/10">{p.image_url ? <img src={p.image_url} alt="" className="w-full h-full object-cover" /> : <Tag className="text-purple-300" size={26} />}</div>
                <div className="p-3">
                  <div className="text-sm font-bold truncate">{p.title}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-base font-black">{money(p.price_cents)}</span>
                    {p.offer && <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-pink-500/20 text-pink-300">{p.offer}</span>}
                  </div>
                  {show.can_manage ? (
                    <button onClick={() => unpin(p.product_id)} data-testid={`live-unpin-${p.product_id}`} className="mt-2 w-full h-9 rounded-full bg-white/[0.06] text-slate-300 text-xs font-bold inline-flex items-center justify-center gap-1.5"><Trash2 size={13} /> Unpin</button>
                  ) : (
                    <button onClick={() => buy(p)} disabled={buying === p.product_id} data-testid={`live-buy-${p.product_id}`} className="mt-2 w-full h-9 rounded-full text-white text-xs font-black inline-flex items-center justify-center gap-1.5" style={grad}>
                      {buying === p.product_id ? <Loader2 size={13} className="animate-spin" /> : <ShoppingBag size={13} />} Buy now
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Shoppable highlight clips */}
      {clips.length > 0 && (
        <div className="mt-5" data-testid="live-clips">
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2 flex items-center gap-1.5"><Scissors size={13} /> Highlight clips</div>
          <div className="space-y-3">
            {clips.map((c) => (
              <div key={c.clip_id} className="rounded-2xl bg-white/[0.04] border border-white/10 p-3" data-testid={`live-clip-${c.clip_id}`}>
                <div className="flex items-center gap-2">
                  <div className="w-9 h-9 rounded-xl grid place-items-center" style={grad}><Sparkles size={16} className="text-white" /></div>
                  <div className="min-w-0"><div className="text-sm font-black truncate">{c.title}</div><div className="text-[11px] text-slate-400 truncate">{c.caption}</div></div>
                </div>
                {c.products?.length > 0 && (
                  <div className="flex gap-2 overflow-x-auto no-scrollbar mt-3">
                    {c.products.map((p) => (
                      <div key={p.product_id} className="flex-shrink-0 w-40 rounded-xl bg-white/[0.04] border border-white/10 p-2.5">
                        <div className="text-xs font-bold truncate">{p.title}</div>
                        <div className="text-sm font-black mt-0.5">{money(p.price_cents)}</div>
                        <button onClick={() => buyClip(c, p)} disabled={buying === p.product_id} data-testid={`clip-buy-${p.product_id}`} className="mt-2 w-full h-8 rounded-full text-white text-[11px] font-black inline-flex items-center justify-center gap-1" style={grad}>{buying === p.product_id ? <Loader2 size={12} className="animate-spin" /> : <ShoppingBag size={12} />} Buy</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Live chat */}
      <div className="mt-5 rounded-3xl bg-white/[0.03] border border-white/10 p-4" data-testid="live-chat">
        <div className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Live chat</div>
        <div className="max-h-56 overflow-y-auto space-y-2 pr-1">
          {messages.length === 0 && <div className="text-sm text-slate-500">Say hi to the host 👋</div>}
          {messages.map((m) => (
            <div key={m.id} className="flex items-start gap-2">
              <Avatar name={m.author?.name} url={m.author?.avatar_url} size={26} />
              <div><span className="text-[11px] font-bold text-slate-300">{m.author?.name}</span> <span className="text-sm text-slate-200">{m.text}</span></div>
            </div>
          ))}
          <div ref={chatEnd} />
        </div>
        <div className="flex items-center gap-2 mt-3">
          <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Chat with the host…"
                 data-testid="live-chat-input" className="flex-1 rounded-full bg-white/[0.05] border border-white/10 px-4 h-10 text-sm outline-none" />
          <button onClick={send} data-testid="live-chat-send" className="w-10 h-10 grid place-items-center rounded-full text-white" style={grad}><Send size={15} /></button>
        </div>
      </div>

      {pinOpen && <PinProductModal onClose={() => setPinOpen(false)} onPin={async (body) => { try { await api.post(`/${showId}/products`, body); setPinOpen(false); loadShow(); toast.success("Product pinned"); } catch (_) { toast.error("Couldn’t pin."); } }} />}
      {cohostOpen && <CohostModal showId={showId} cohosts={show.cohosts || []} onClose={() => setCohostOpen(false)} onChange={loadShow} />}
    </div>
  );
}

function CohostModal({ showId, cohosts, onClose, onChange }) {
  const [friends, setFriends] = useState([]);
  useEffect(() => {
    axios.get(`${B}/api/social/friends`, { withCredentials: true })
      .then(({ data }) => setFriends(data.friends || [])).catch(() => {});
  }, []);
  const coIds = new Set(cohosts.map((c) => c.user_id));
  const add = async (uid) => { try { await api.post(`/${showId}/cohosts`, { user_id: uid }); onChange(); toast.success("Co-host added"); } catch (_) { toast.error("Couldn’t add co-host."); } };
  const remove = async (uid) => { try { await api.delete(`/${showId}/cohosts/${uid}`); onChange(); } catch (_) {} };
  return (
    <Modal title="Invite a co-host" onClose={onClose} testid="cohost-modal">
      {friends.length === 0 ? (
        <div className="text-sm text-slate-400">Add friends first to invite a co-host.</div>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {friends.map((f) => (
            <div key={f.user_id} className="flex items-center gap-3 rounded-2xl bg-white/[0.04] border border-white/10 px-3 py-2">
              <Avatar name={f.name} url={f.avatar_url} size={34} />
              <span className="flex-1 text-sm font-bold truncate">{f.name}</span>
              {coIds.has(f.user_id) ? (
                <button onClick={() => remove(f.user_id)} data-testid={`cohost-remove-${f.user_id}`} className="text-xs font-bold text-slate-400 px-3 h-8 rounded-full bg-white/[0.06]">Remove</button>
              ) : (
                <button onClick={() => add(f.user_id)} data-testid={`cohost-add-${f.user_id}`} className="text-xs font-black text-white px-3 h-8 rounded-full" style={grad}>Add</button>
              )}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

function PinProductModal({ onClose, onPin }) {
  const [title, setTitle] = useState("");
  const [price, setPrice] = useState("");
  const [offer, setOffer] = useState("");
  const [image, setImage] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (title.trim().length < 1) { toast.info("Add a product title."); return; }
    setBusy(true);
    await onPin({ title, price_cents: Math.round(parseFloat(price || "0") * 100), offer, image_url: image || null });
    setBusy(false);
  };
  return (
    <Modal title="Pin a product" onClose={onClose} testid="pin-product-modal">
      <div className="space-y-3">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Product title" data-testid="pin-title" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        <input value={price} onChange={(e) => setPrice(e.target.value)} placeholder="Price (USD, e.g. 24.99)" inputMode="decimal" data-testid="pin-price" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        <input value={offer} onChange={(e) => setOffer(e.target.value)} placeholder="Live offer (optional, e.g. -20%)" data-testid="pin-offer" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        <input value={image} onChange={(e) => setImage(e.target.value)} placeholder="Image URL (optional)" data-testid="pin-image" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        <button onClick={submit} disabled={busy} data-testid="pin-submit" className="w-full h-11 rounded-full text-white font-black inline-flex items-center justify-center gap-2" style={grad}>
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />} Pin to show
        </button>
      </div>
    </Modal>
  );
}

function Modal({ title, onClose, children, testid }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 p-0 sm:p-5" onClick={onClose} data-testid={testid}>
      <div onClick={(e) => e.stopPropagation()} className="w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl border border-white/10 p-5" style={{ background: "linear-gradient(180deg,#12131f,#0b0c16)" }}>
        <div className="flex items-center justify-between mb-4"><h3 className="text-xl font-black text-white">{title}</h3>
          <button onClick={onClose} className="w-9 h-9 grid place-items-center rounded-full bg-white/[0.06]"><X size={18} /></button></div>
        {children}
      </div>
    </div>
  );
}
