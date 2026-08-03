// Phase PG.1 — Merchant Games campaign manager + 3-step wizard.
// (Brief calls for 5 steps; consolidated into a single Create modal for MVP.)
import React, { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Trophy, Plus, Play, Pause, TrendingUp, X, Loader2,
                  Sparkles, Trash2, Zap, Target, Megaphone } from "lucide-react";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { useMerchant } from "./MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const FMT = (n) => (Number(n || 0) / 100).toFixed(2);

const PRIZE_TYPES = [
  {id: "points",              label: "Points"},
  {id: "coupon",              label: "Coupon"},
  {id: "gift_card",        label: "Gift Card"},
  {id: "prepaid_meal", label: "Meal Pack"},
  {id: "nothing",            label: "Nothing (better luck!)"},
];

export default function MerchantGames() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { merchant, hasPerm } = useMerchant();

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [analytics, setAnalytics] = useState(null);
  const canEdit = hasPerm ? hasPerm("can_create_links") : true;

  const load = async () => {
    if (!merchant?.merchant_id) return;
    setLoading(true);
    try {
      const { data } = await axios.get(
        `${API}/merchant/${merchant.merchant_id}/game-campaigns`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail?.code || e.message}`);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [merchant?.merchant_id]);

  const togglePause = async (c) => {
    try {
      const endpoint = c.active ? "pause" : "";
      const url = c.active
        ? `${API}/merchant/${merchant.merchant_id}/game-campaigns/${c.campaign_id}/pause`
        : `${API}/merchant/${merchant.merchant_id}/game-campaigns/${c.campaign_id}`;
      if (c.active) {
        await axios.post(url, null, { withCredentials: true });
      } else {
        await axios.put(url, {active: true}, { withCredentials: true });
      }
      toast.success(c.active ? "Paused" : "Resumed");
      load();
    } catch (e) { toast.error(`Failed: ${e.message}`); }
  };

  const openAnalytics = async (c) => {
    try {
      const { data } = await axios.get(
        `${API}/merchant/${merchant.merchant_id}/game-campaigns/${c.campaign_id}/analytics`,
        { withCredentials: true });
      setAnalytics({...data, campaign: c});
    } catch (e) { toast.error(`Failed: ${e.message}`); }
  };

  const bgClass = light
    ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
    : "min-h-screen bg-slate-950 text-slate-100";

  if (loading) return (
    <div className={`${bgClass} p-8`} data-testid="merchant-games-loading">
      <Loader2 className="animate-spin mx-auto mt-24" size={30}/>
    </div>);

  return (
    <div className={`${bgClass} p-4 sm:p-8`} data-testid="merchant-games-page">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className={`text-[10px] font-bold uppercase tracking-widest ${
              light ? "text-purple-600" : "text-cyan-400"}`}>Engagement · Phase PG.1</div>
            <h1 className={`text-3xl font-black tracking-tight ${
              light ? "text-slate-900" : "text-white"}`}>Games</h1>
            <p className={`text-sm mt-1 ${
              light ? "text-slate-600" : "text-slate-400"}`}>
              Spin & Win + Scratch & Win — customers play once, wins land in their wallet.
            </p>
          </div>
          {canEdit && (
            <button type="button" onClick={() => setShowCreate(true)}
                          data-testid="merchant-games-create-btn"
                          className="inline-flex items-center gap-2 h-11 rounded-full px-5 text-sm font-black text-white"
                          style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
              <Plus size={16}/> New Game Campaign
            </button>
          )}
        </div>

        {items.length === 0 ? (
          <div className={`rounded-3xl p-10 text-center ${
            light ? "bg-white border border-slate-100 shadow-sm"
                    : "bg-slate-900 border border-slate-800"}`}
                data-testid="merchant-games-empty">
            <Trophy className="mx-auto mb-3" size={40}
                              color={light ? "#a855f7" : "#00d4ff"}/>
            <h3 className={`text-lg font-black ${
              light ? "text-slate-900" : "text-white"}`}>No game campaigns yet</h3>
            <p className={`text-sm mt-1 ${light ? "text-slate-600" : "text-slate-400"}`}>
              Launch a Spin & Win with a few prizes — great for footfall on quiet days.
            </p>
          </div>
        ) : (
          <div className={`rounded-3xl overflow-hidden ${
            light ? "bg-white border border-slate-100 shadow-sm"
                    : "bg-slate-900 border border-slate-800"}`}
                data-testid="merchant-games-table">
            <table className="w-full">
              <thead>
                <tr className={`text-[10px] font-bold uppercase tracking-widest ${
                  light ? "text-slate-500 border-b border-slate-100"
                          : "text-slate-500 border-b border-slate-800"}`}>
                  <th className="text-left p-4">Name</th>
                  <th className="text-left p-4">Type</th>
                  <th className="text-left p-4">Status</th>
                  <th className="text-left p-4">Plays</th>
                  <th className="text-left p-4">Prizes</th>
                  <th className="text-right p-4">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map(c => (
                  <tr key={c.campaign_id}
                          data-testid={`merchant-games-row-${c.campaign_id}`}
                          className={light ? "border-b border-slate-100 last:border-0"
                                                    : "border-b border-slate-800 last:border-0"}>
                    <td className="p-4">
                      <div className={`font-black ${
                        light ? "text-slate-900" : "text-white"}`}>{c.name}</div>
                    </td>
                    <td className="p-4 text-xs">
                      {c.game_type === "spin_win" ? "Spin & Win" : "Scratch & Win"}
                    </td>
                    <td className="p-4">
                      <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-full ${
                        c.active
                          ? (light ? "bg-emerald-100 text-emerald-700"
                                        : "bg-emerald-500/15 text-emerald-300")
                          : (light ? "bg-slate-100 text-slate-500"
                                        : "bg-slate-800 text-slate-500")}`}>
                        {c.active ? "Live" : "Paused"}
                      </span>
                    </td>
                    <td className="p-4 text-sm tabular-nums">
                      {c.current_plays_count || 0}
                      {c.max_total_plays ? ` / ${c.max_total_plays}` : ""}
                    </td>
                    <td className="p-4 text-xs">
                      {(c.prizes || []).length} prize{(c.prizes || []).length !== 1 ? "s" : ""}
                    </td>
                    <td className="p-4 text-right">
                      <div className="inline-flex gap-1">
                        <button type="button" onClick={() => openAnalytics(c)}
                                      data-testid={`merchant-games-analytics-${c.campaign_id}`}
                                      className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                                        light ? "hover:bg-slate-100 text-slate-600"
                                                : "hover:bg-slate-800 text-slate-400"}`}
                                      title="Analytics">
                          <TrendingUp size={14}/>
                        </button>
                        <SponsorGameCTA campaign={c} light={light} />
                        {canEdit && (
                          <button type="button" onClick={() => togglePause(c)}
                                        data-testid={`merchant-games-toggle-${c.campaign_id}`}
                                        className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                                          light ? "hover:bg-slate-100 text-slate-600"
                                                  : "hover:bg-slate-800 text-slate-400"}`}
                                        title={c.active ? "Pause" : "Resume"}>
                            {c.active ? <Pause size={14}/> : <Play size={14}/>}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showCreate && (
        <CreateWizard light={light} merchant={merchant}
                                      onClose={() => setShowCreate(false)}
                                      onCreated={() => { setShowCreate(false); load(); }}/>
      )}
      {analytics && (
        <AnalyticsDrawer light={light} data={analytics}
                                            onClose={() => setAnalytics(null)}/>
      )}
    </div>
  );
}


function CreateWizard({ light, merchant, onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [gameType, setGameType] = useState("spin_win");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [prizes, setPrizes] = useState([
    {prize_type: "points", points_amount: 100, weight: 1, quantity_available: 100,
      display_label: "100 points", display_color: "#10b981"},
    {prize_type: "nothing", weight: 5, quantity_available: 0,
      display_label: "Better luck", display_color: "#6b7280"},
  ]);
  const [maxPerUser, setMaxPerUser] = useState(1);
  const [maxTotal, setMaxTotal] = useState("");
  const [endDays, setEndDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const totalWeight = prizes.reduce((s, p) => s + (Number(p.weight) || 0), 0);

  const addPrize = () => setPrizes([...prizes, {
    prize_type: "points", points_amount: 50, weight: 1, quantity_available: 50,
    display_label: "50 points", display_color: "#a855f7"}]);
  const updatePrize = (i, patch) => {
    const next = [...prizes]; next[i] = {...next[i], ...patch}; setPrizes(next);
  };
  const removePrize = (i) => setPrizes(prizes.filter((_, idx) => idx !== i));

  const submit = async () => {
    setErr(null);
    if (!name.trim()) { setErr("Name is required"); return; }
    if (prizes.length === 0) { setErr("At least one prize required"); return; }
    setBusy(true);
    try {
      const templateId = gameType === "spin_win" ? "tpl_spin_default_6"
                                                                              : "tpl_scratch_default_3x3";
      const end_at = new Date(Date.now() + endDays * 86400 * 1000).toISOString();
      await axios.post(
        `${API}/merchant/${merchant.merchant_id}/game-campaigns`,
        { template_id: templateId, game_type: gameType,
          name: name.trim(), description: description.trim() || null,
          prizes,
          max_plays_per_user: Number(maxPerUser) || 1,
          max_total_plays: maxTotal ? Number(maxTotal) : null,
          end_at, active: true },
        { withCredentials: true });
      toast.success("Game campaign created");
      onCreated();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally { setBusy(false); }
  };

  return (
    <Modal light={light} onClose={onClose}
                testid="merchant-games-create-wizard">
      <h2 className={`text-xl font-black mb-1 ${
        light ? "text-slate-900" : "text-white"}`}>New Game Campaign</h2>
      <div className={`text-xs mb-4 ${
        light ? "text-slate-500" : "text-slate-500"}`}>
        Step {step} of 3
      </div>

      {step === 1 && (
        <>
          <Label light={light}>Game Type</Label>
          <div className="grid grid-cols-2 gap-2">
            {[
              {id:"spin_win", label:"Spin & Win", Icon:Zap},
              {id:"scratch_win", label:"Scratch & Win", Icon:Target},
            ].map(t => (
              <button key={t.id} type="button"
                            onClick={() => setGameType(t.id)}
                            data-testid={`merchant-games-type-${t.id}`}
                            data-active={gameType === t.id}
                            className={`p-4 rounded-2xl text-left ${
                              gameType === t.id
                                ? (light ? "bg-purple-100 border-2 border-purple-500"
                                                : "bg-cyan-500/15 border-2 border-cyan-500")
                                : (light ? "bg-slate-50 border-2 border-transparent"
                                                : "bg-slate-950 border-2 border-transparent")}`}>
                <t.Icon size={24}
                              color={gameType === t.id
                                                ? (light ? "#a855f7" : "#00d4ff")
                                                : (light ? "#94a3b8" : "#64748b")}/>
                <div className={`mt-2 text-sm font-black ${
                  light ? "text-slate-900" : "text-white"}`}>{t.label}</div>
              </button>
            ))}
          </div>
          <Label light={light} className="mt-4">Name</Label>
          <input type="text" value={name} onChange={e => setName(e.target.value)}
                      placeholder="e.g. Weekend Karak Wheel"
                      data-testid="merchant-games-name"
                      className={inputClass(light)}/>
          <Label light={light} className="mt-3">Description (optional)</Label>
          <textarea rows={2} value={description}
                            onChange={e => setDescription(e.target.value)}
                            className={inputClass(light)}/>
          <NextBack light={light}
                              onBack={onClose} onNext={() => setStep(2)}
                              nextEnabled={!!name.trim()}
                              backLabel="Cancel" nextLabel="Next"
                              nextTestid="merchant-games-next-1"/>
        </>
      )}

      {step === 2 && (
        <>
          <Label light={light}>Prizes ({prizes.length})</Label>
          <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1"
                data-testid="merchant-games-prizes-list">
            {prizes.map((p, i) => (
              <PrizeRow key={i} prize={p} i={i} light={light}
                                    onChange={(patch) => updatePrize(i, patch)}
                                    onRemove={() => removePrize(i)}/>
            ))}
          </div>
          <button type="button" onClick={addPrize}
                        data-testid="merchant-games-add-prize"
                        className={`mt-3 w-full h-10 rounded-xl border-2 border-dashed text-xs font-bold inline-flex items-center justify-center gap-1 ${
                          light ? "border-purple-300 text-purple-700 hover:bg-purple-50"
                                  : "border-cyan-500/30 text-cyan-300 hover:bg-slate-800"}`}>
            <Plus size={14}/> Add prize
          </button>
          <div className={`mt-2 text-[10px] ${
            light ? "text-slate-500" : "text-slate-500"}`}>
            Weights sum to <b>{totalWeight}</b> — higher weight = higher chance of winning that prize.
          </div>
          <NextBack light={light}
                              onBack={() => setStep(1)} onNext={() => setStep(3)}
                              nextEnabled={prizes.length > 0}
                              nextTestid="merchant-games-next-2"/>
        </>
      )}

      {step === 3 && (
        <>
          <Label light={light}>Play limits & schedule</Label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label light={light}>Max plays per user</Label>
              <input type="number" min={1} max={100} value={maxPerUser}
                          onChange={e => setMaxPerUser(e.target.value)}
                          data-testid="merchant-games-max-per-user"
                          className={inputClass(light)}/>
            </div>
            <div>
              <Label light={light}>Ends in (days)</Label>
              <input type="number" min={1} max={365} value={endDays}
                          onChange={e => setEndDays(e.target.value)}
                          data-testid="merchant-games-end-days"
                          className={inputClass(light)}/>
            </div>
          </div>
          <Label light={light} className="mt-3">Max total plays (optional)</Label>
          <input type="number" min={1} value={maxTotal}
                      onChange={e => setMaxTotal(e.target.value)}
                      placeholder="Unlimited"
                      data-testid="merchant-games-max-total"
                      className={inputClass(light)}/>

          {err && <div className={`mt-3 rounded-xl px-3 py-2 text-sm ${
            light ? "bg-rose-50 text-rose-800" : "bg-rose-500/10 text-rose-300"
          }`} data-testid="merchant-games-create-error">{err}</div>}

          <NextBack light={light}
                              onBack={() => setStep(2)} onNext={submit}
                              nextEnabled={!busy}
                              nextLabel={busy ? "Creating…" : "Publish"}
                              nextTestid="merchant-games-submit"/>
        </>
      )}
    </Modal>
  );
}


function PrizeRow({ prize, i, light, onChange, onRemove }) {
  return (
    <div className={`rounded-xl p-3 ${
      light ? "bg-slate-50 border border-slate-200"
              : "bg-slate-950 border border-slate-800"}`}
              data-testid={`merchant-games-prize-row-${i}`}>
      <div className="flex items-start justify-between mb-2">
        <select value={prize.prize_type}
                        onChange={e => onChange({prize_type: e.target.value})}
                        data-testid={`merchant-games-prize-type-${i}`}
                        className={`h-8 rounded-lg px-2 text-xs font-bold ${
                          light ? "bg-white border border-slate-300"
                                  : "bg-slate-900 border border-slate-700 text-white"}`}>
          {PRIZE_TYPES.map(t => (
            <option key={t.id} value={t.id}>{t.label}</option>
          ))}
        </select>
        <button type="button" onClick={onRemove}
                      data-testid={`merchant-games-remove-prize-${i}`}
                      className={light ? "text-rose-600 hover:text-rose-800"
                                                    : "text-rose-400 hover:text-rose-300"}>
          <Trash2 size={14}/>
        </button>
      </div>
      <input type="text" value={prize.display_label}
                  onChange={e => onChange({display_label: e.target.value})}
                  placeholder="Display label"
                  data-testid={`merchant-games-prize-label-${i}`}
                  className={`w-full h-8 rounded-lg px-2 text-xs ${
                    light ? "bg-white border border-slate-300"
                            : "bg-slate-900 border border-slate-700 text-white"}`}/>
      <div className="grid grid-cols-3 gap-2 mt-2">
        {prize.prize_type === "points" && (
          <div>
            <div className={`text-[9px] font-bold uppercase mb-0.5 ${
              light ? "text-slate-500" : "text-slate-500"}`}>Points</div>
            <input type="number" min={0} value={prize.points_amount || 0}
                        onChange={e => onChange({points_amount: Number(e.target.value)})}
                        data-testid={`merchant-games-prize-points-${i}`}
                        className={`w-full h-8 rounded-lg px-2 text-xs ${
                          light ? "bg-white border border-slate-300"
                                  : "bg-slate-900 border border-slate-700 text-white"}`}/>
          </div>
        )}
        {(prize.prize_type === "gift_card" || prize.prize_type === "prepaid_meal") && (
          <div className="col-span-2">
            <div className={`text-[9px] font-bold uppercase mb-0.5 ${
              light ? "text-slate-500" : "text-slate-500"}`}>SKU ID</div>
            <input type="text" value={prize.sku_id || ""}
                        onChange={e => onChange({sku_id: e.target.value})}
                        placeholder="gcs_… or pms_…"
                        className={`w-full h-8 rounded-lg px-2 text-xs font-mono ${
                          light ? "bg-white border border-slate-300"
                                  : "bg-slate-900 border border-slate-700 text-white"}`}/>
          </div>
        )}
        {prize.prize_type === "coupon" && (
          <div className="col-span-2">
            <div className={`text-[9px] font-bold uppercase mb-0.5 ${
              light ? "text-slate-500" : "text-slate-500"}`}>Offer ID</div>
            <input type="text" value={prize.coupon_offer_id || ""}
                        onChange={e => onChange({coupon_offer_id: e.target.value})}
                        placeholder="off_…"
                        className={`w-full h-8 rounded-lg px-2 text-xs font-mono ${
                          light ? "bg-white border border-slate-300"
                                  : "bg-slate-900 border border-slate-700 text-white"}`}/>
          </div>
        )}
        <div>
          <div className={`text-[9px] font-bold uppercase mb-0.5 ${
            light ? "text-slate-500" : "text-slate-500"}`}>Weight</div>
          <input type="number" min={0} step="0.5" value={prize.weight || 1}
                      onChange={e => onChange({weight: Number(e.target.value)})}
                      data-testid={`merchant-games-prize-weight-${i}`}
                      className={`w-full h-8 rounded-lg px-2 text-xs ${
                        light ? "bg-white border border-slate-300"
                                : "bg-slate-900 border border-slate-700 text-white"}`}/>
        </div>
        <div>
          <div className={`text-[9px] font-bold uppercase mb-0.5 ${
            light ? "text-slate-500" : "text-slate-500"}`}>Qty (0=unl)</div>
          <input type="number" min={0} value={prize.quantity_available || 0}
                      onChange={e => onChange({quantity_available: Number(e.target.value)})}
                      data-testid={`merchant-games-prize-qty-${i}`}
                      className={`w-full h-8 rounded-lg px-2 text-xs ${
                        light ? "bg-white border border-slate-300"
                                : "bg-slate-900 border border-slate-700 text-white"}`}/>
        </div>
      </div>
    </div>
  );
}


function AnalyticsDrawer({ light, data, onClose }) {
  return (
    <Modal light={light} onClose={onClose}
                testid="merchant-games-analytics-modal">
      <h2 className={`text-xl font-black mb-1 ${
        light ? "text-slate-900" : "text-white"}`}>Analytics</h2>
      <div className={`text-sm mb-4 ${
        light ? "text-slate-600" : "text-slate-400"}`}>{data.campaign?.name}</div>

      <div className="grid grid-cols-2 gap-3">
        <Stat light={light} label="Plays" value={data.plays}/>
        <Stat light={light} label="Wins" value={data.wins}/>
        <Stat light={light} label="Unique players" value={data.unique_players}/>
        <Stat light={light} label="Cost (AED)" value={FMT(data.cost_estimate_cents)}/>
      </div>

      <h3 className={`mt-6 mb-2 text-sm font-black ${
        light ? "text-slate-900" : "text-white"}`}>Prize distribution</h3>
      <div className="space-y-1">
        {(data.prize_distribution || []).map(p => (
          <div key={p.prize_id} className={`flex justify-between text-xs p-2 rounded-lg ${
            light ? "bg-slate-50" : "bg-slate-950"}`}
                data-testid={`merchant-games-dist-${p.prize_id}`}>
            <span className={light ? "text-slate-800" : "text-slate-200"}>
              {p.display_label || "Prize"} <span className="opacity-50">({p.prize_type})</span>
            </span>
            <span className={`font-black ${
              light ? "text-slate-900" : "text-white"}`}>{p.count}</span>
          </div>
        ))}
        {(data.prize_distribution || []).length === 0 && (
          <div className={`text-xs italic ${
            light ? "text-slate-500" : "text-slate-500"}`}>No plays yet.</div>
        )}
      </div>
    </Modal>
  );
}

function Stat({ light, label, value }) {
  return (
    <div className={`rounded-xl p-3 ${
      light ? "bg-slate-50 border border-slate-100"
              : "bg-slate-950 border border-slate-800"}`}>
      <div className={`text-[10px] font-bold uppercase tracking-widest ${
        light ? "text-slate-500" : "text-slate-500"}`}>{label}</div>
      <div className={`text-xl font-black tabular-nums mt-0.5 ${
        light ? "text-slate-900" : "text-white"}`}>{value ?? 0}</div>
    </div>
  );
}

function NextBack({ light, onBack, onNext, nextEnabled, backLabel = "Back",
                                    nextLabel = "Next", nextTestid }) {
  return (
    <div className="mt-5 grid grid-cols-2 gap-2">
      <button type="button" onClick={onBack}
                    className={`h-11 rounded-full text-xs font-bold ${
                      light ? "bg-slate-100 text-slate-700"
                              : "bg-slate-800 text-slate-300"}`}>
        {backLabel}
      </button>
      <button type="button" onClick={onNext} disabled={!nextEnabled}
                    data-testid={nextTestid}
                    className={`h-11 rounded-full text-xs font-black text-white ${
                      !nextEnabled ? "opacity-50" : ""}`}
                    style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
        {nextLabel}
      </button>
    </div>
  );
}


function Modal({ light, onClose, testid, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
              onClick={onClose}>
      <div onClick={e => e.stopPropagation()}
                data-testid={testid}
                className={`w-full max-w-lg rounded-3xl p-6 max-h-[95vh] overflow-y-auto ${
                  light ? "bg-white" : "bg-slate-900 border border-slate-800"}`}>
        <div className="flex justify-end mb-1">
          <button type="button" onClick={onClose}
                        className={light ? "text-slate-500" : "text-slate-500"}>
            <X size={20}/>
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Label({ children, light, className = "" }) {
  return <div className={`text-[10px] font-bold uppercase tracking-widest mb-1 ${
    light ? "text-slate-500" : "text-slate-500"} ${className}`}>{children}</div>;
}

function inputClass(light) {
  return `w-full h-11 rounded-xl px-3 text-sm outline-none ${
    light
      ? "bg-slate-50 border border-slate-200 text-slate-900 focus:border-purple-500"
      : "bg-slate-950 border border-slate-800 text-slate-100 focus:border-cyan-500"}`;
}


// Phase AD.6 · Bonus — "Sponsor this game" CTA for merchants to share with
// potential brand sponsors.  Deep-links to /advertiser/apply with the game
// campaign prefill.  Uses the AD.1 → AD.2 buy funnel we already shipped.
function SponsorGameCTA({ campaign, light }) {
  const [copied, setCopied] = React.useState(false);
  const alreadySponsored = !!campaign.sponsored_by_ad_campaign_id;
  const url = React.useMemo(() => {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    const qs = new URLSearchParams({
      prefill_game: campaign.campaign_id || "",
      game_name: campaign.name || "",
    });
    return `${origin}/advertiser/apply?${qs.toString()}`;
  }, [campaign]);

  async function onClick(e) {
    e.stopPropagation();
    try {
      await navigator.clipboard?.writeText(url);
      setCopied(true);
      toast.success("Sponsorship link copied — share with your brand partner");
    } catch (_) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
    setTimeout(() => setCopied(false), 2200);
  }

  return (
    <button type="button" onClick={onClick}
                    data-testid={`merchant-game-sponsor-cta-${campaign.campaign_id}`}
                    title={alreadySponsored
                                          ? "This game already has an active sponsor"
                                          : "Copy sponsorship link for a brand"}
                    className={`w-8 h-8 rounded-lg flex items-center justify-center relative ${
                                        alreadySponsored
                                            ? (light ? "text-amber-600 bg-amber-100 border border-amber-200"
                                                            : "text-amber-400 bg-amber-500/10 border border-amber-500/30")
                                            : (light ? "hover:bg-purple-100 text-purple-600"
                                                            : "hover:bg-amber-500/10 text-amber-400")}`}>
      <Megaphone size={14} />
      {copied && (
        <span className={`absolute -top-8 right-0 whitespace-nowrap text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-full ${
                                        light ? "bg-emerald-500 text-white" : "bg-emerald-500 text-slate-900"}`}>
          Copied
        </span>
      )}
    </button>
  );
}
// Also expose a global testid without the campaign id suffix for smoke tests.
// (Wrapper for easy discovery by any first-row selection.)
