/** Phase 42 S1 — Advertiser Buy-Slot 5-step wizard + My Campaigns. */
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, ChevronRight, Upload, Check, ShoppingCart } from "lucide-react";
import { API } from "@/AuthContext";

const SLOTS = [
  { slot_key: "top_leaderboard", size: "970x90",  cpm: 4.50,
    coverage: "Home · Channels · News · Wallet · Commute · Places · Passport" },
  { slot_key: "right_rail",      size: "160x600", cpm: 3.20,
    coverage: "Home · Channels · News" },
  { slot_key: "left_rail",       size: "160x600", cpm: 2.80,
    coverage: "Home · Channels" },
  { slot_key: "center_mid",      size: "300x250", cpm: 3.60,
    coverage: "Home · Channels · News · Wallet" },
];

const STEPS = ["Slot", "Creative", "Schedule & Budget", "Targeting", "Checkout"];
const inputS = { width: "100%", padding: "8px 12px", borderRadius: 8,
                 background: "rgba(255,255,255,0.05)", color: "#fff",
                 border: "1px solid rgba(255,255,255,0.08)", fontSize: 14 };
const btnP   = { background: "#00d9ff", color: "#0b0b0b", border: "none",
                 padding: "10px 18px", borderRadius: 8, fontWeight: 600,
                 cursor: "pointer", fontSize: 14, display: "inline-flex",
                 alignItems: "center", gap: 6 };
const btnS   = { background: "rgba(255,255,255,0.06)", color: "#fff",
                 border: "1px solid rgba(255,255,255,0.08)",
                 padding: "8px 14px", borderRadius: 8, cursor: "pointer",
                 fontSize: 13, display: "inline-flex", alignItems: "center", gap: 4 };


function validateImageDims(file, sizeStr) {
  const [w, h] = sizeStr.split("x").map(Number);
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => {
      if (img.width === w && img.height === h) res({ ok: true });
      else rej({ code: "dim_mismatch", got: `${img.width}x${img.height}`,
                  expected: sizeStr });
    };
    img.onerror = () => rej({ code: "bad_image" });
    img.src = URL.createObjectURL(file);
  });
}


export function BuyBannerSlot() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [picked, setPicked] = useState([]);
  const [creativeUrl, setCreativeUrl] = useState("");
  const [clickUrl, setClickUrl] = useState("");
  const [startDate, setStartDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [endDate, setEndDate]     = useState(() => new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10));
  const [dailyBudget, setDB] = useState(50);
  const [totalBudget, setTB] = useState(350);
  const [targeting, setTargeting] = useState({ city: "", language: "", tier: "all", daypart: "any" });
  const [freqCap, setFC] = useState(5);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const togglePick = (sk) =>
    setPicked(p => p.includes(sk) ? p.filter(x => x !== sk) : [...p, sk]);

  const onCreative = async (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    setErr(null);
    if (picked.length !== 1) {
      setErr("Pick exactly one slot for now (multi-slot in roadmap)."); return;
    }
    const sz = SLOTS.find(s => s.slot_key === picked[0])?.size;
    try {
      await validateImageDims(f, sz);
      // Upload via existing creative upload route; falls back to data-URL preview if not wired.
      const fd = new FormData(); fd.append("file", f);
      try {
        const r = await axios.post(`${API}/uploads/creative`, fd,
          { withCredentials: true, headers: { "Content-Type": "multipart/form-data" } });
        setCreativeUrl(r.data?.url || URL.createObjectURL(f));
      } catch (_) {
        setCreativeUrl(URL.createObjectURL(f));  // local preview
      }
    } catch (e) {
      setErr(e.code === "dim_mismatch"
              ? `Image must be ${e.expected}, got ${e.got}.`
              : "Invalid image.");
    }
  };

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await axios.post(`${API}/ads/advertiser/banner-campaigns`,
        { slot_keys: picked,
          creative_image_url: creativeUrl,
          click_url: clickUrl,
          start_date: startDate, end_date: endDate,
          daily_budget: Number(dailyBudget),
          total_budget: Number(totalBudget),
          targeting_json: targeting,
          frequency_cap_per_user_per_day: Number(freqCap) },
        { withCredentials: true });
      const cid = r.data.campaign_id;
      const co = await axios.post(`${API}/ads/advertiser/banner-campaigns/${cid}/checkout`,
        {}, { withCredentials: true });
      window.location.href = co.data.checkout_url || `/advertiser/banner/campaigns`;
    } catch (e) {
      setErr(e.response?.data?.detail?.code || "Submit failed");
    }
    setBusy(false);
  };

  return (
    <div data-testid="buy-banner-page"
         style={{ maxWidth: 820, margin: "0 auto", padding: 24, color: "#fff" }}>
      <h1 style={{ display: "flex", alignItems: "center", gap: 10,
                   fontSize: 26, fontWeight: 700, margin: "0 0 8px" }}>
        <ShoppingCart size={22} color="#00d9ff" /> Buy Banner Slot
      </h1>
      <p style={{ color: "#9aa3af", fontSize: 13, marginBottom: 16 }}>
        Step {step + 1} of {STEPS.length} · {STEPS[step]}
      </p>
      <div style={{ height: 4, background: "rgba(255,255,255,0.08)",
                     borderRadius: 2, marginBottom: 22 }}>
        <div style={{ height: 4, width: `${((step + 1) / STEPS.length) * 100}%`,
                       background: "#00d9ff", borderRadius: 2, transition: "width 0.2s" }} />
      </div>
      {err && <div style={{ background: "rgba(239,68,68,0.1)", color: "#fca5a5",
                              padding: "8px 12px", borderRadius: 6, fontSize: 13,
                              marginBottom: 14 }}>{err}</div>}

      {step === 0 && (
        <div data-testid="buy-step-0">
          {SLOTS.map(s => (
            <button key={s.slot_key} data-testid={`buy-slot-${s.slot_key}`}
                    onClick={() => togglePick(s.slot_key)}
                    style={{ width: "100%", textAlign: "left", padding: 14,
                             marginBottom: 10, borderRadius: 10,
                             background: picked.includes(s.slot_key)
                                            ? "rgba(0,217,255,0.12)" : "rgba(255,255,255,0.04)",
                             border: `1px solid ${picked.includes(s.slot_key)
                                            ? "#00d9ff" : "rgba(255,255,255,0.05)"}`,
                             color: "#fff", cursor: "pointer" }}>
              <div style={{ display: "flex", justifyContent: "space-between",
                              fontWeight: 600, fontSize: 14 }}>
                <span>{s.slot_key}</span>
                <span style={{ color: "#00d9ff" }}>${s.cpm.toFixed(2)} CPM</span>
              </div>
              <div style={{ color: "#9aa3af", fontSize: 12, marginTop: 4 }}>
                {s.size} · {s.coverage}
              </div>
            </button>
          ))}
        </div>
      )}

      {step === 1 && (
        <div data-testid="buy-step-1" style={{ display: "grid", gap: 12 }}>
          <div style={{ color: "#9aa3af", fontSize: 13 }}>
            Upload creative — must match exactly{" "}
            <strong>{picked.map(sk => SLOTS.find(s=>s.slot_key===sk)?.size).join(" / ") || "(pick a slot first)"}</strong>.
          </div>
          <input type="file" accept="image/*" data-testid="buy-creative-upload"
                  onChange={onCreative} style={{ ...inputS, padding: 10 }} />
          {creativeUrl && (
            <img src={creativeUrl} alt="" style={{ maxWidth: 320, maxHeight: 240,
                                                    border: "1px solid rgba(255,255,255,0.1)",
                                                    borderRadius: 6 }} />
          )}
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af", marginBottom: 4 }}>Click-through URL</div>
            <input data-testid="buy-click-url" value={clickUrl}
                    onChange={e => setClickUrl(e.target.value)}
                    style={inputS} placeholder="https://example.com/your-landing" />
          </label>
        </div>
      )}

      {step === 2 && (
        <div data-testid="buy-step-2" style={{ display: "grid", gap: 12 }}>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af" }}>Start date</div>
            <input type="date" data-testid="buy-start" value={startDate}
                    onChange={e => setStartDate(e.target.value)} style={inputS} />
          </label>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af" }}>End date</div>
            <input type="date" data-testid="buy-end" value={endDate}
                    onChange={e => setEndDate(e.target.value)} style={inputS} />
          </label>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af" }}>Daily budget ($)</div>
            <input type="number" data-testid="buy-daily" value={dailyBudget}
                    onChange={e => setDB(e.target.value)} style={inputS} />
          </label>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af" }}>Total budget ($)</div>
            <input type="number" data-testid="buy-total" value={totalBudget}
                    onChange={e => setTB(e.target.value)} style={inputS} />
          </label>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af" }}>Frequency cap (per user / day)</div>
            <input type="number" data-testid="buy-freq" value={freqCap}
                    onChange={e => setFC(e.target.value)} style={inputS} />
          </label>
        </div>
      )}

      {step === 3 && (
        <div data-testid="buy-step-3" style={{ display: "grid", gap: 12 }}>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af" }}>City (blank = all)</div>
            <input data-testid="buy-city" value={targeting.city}
                    onChange={e => setTargeting(t => ({ ...t, city: e.target.value }))}
                    style={inputS} placeholder="e.g. Dallas" />
          </label>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af" }}>Language</div>
            <input data-testid="buy-lang" value={targeting.language}
                    onChange={e => setTargeting(t => ({ ...t, language: e.target.value }))}
                    style={inputS} placeholder="en, hi, …" />
          </label>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af" }}>Tier</div>
            <select data-testid="buy-tier" value={targeting.tier}
                    onChange={e => setTargeting(t => ({ ...t, tier: e.target.value }))}
                    style={inputS}>
              <option value="all">All listeners</option>
              <option value="free">Free only</option>
              <option value="premium">Premium only</option>
            </select>
          </label>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af" }}>Daypart</div>
            <select data-testid="buy-daypart" value={targeting.daypart}
                    onChange={e => setTargeting(t => ({ ...t, daypart: e.target.value }))}
                    style={inputS}>
              <option value="any">Anytime</option>
              <option value="drive_morning">Morning rush (7-9:30 local)</option>
              <option value="drive_evening">Evening rush (17-19:30 local)</option>
              <option value="lunch">Lunch (12-14)</option>
              <option value="night">Night (21-24)</option>
            </select>
          </label>
        </div>
      )}

      {step === 4 && (
        <div data-testid="buy-step-4" style={{ padding: 16, borderRadius: 12,
                                                background: "rgba(255,255,255,0.04)" }}>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Review</div>
          <div style={{ fontSize: 13, marginBottom: 4 }}>Slot(s): {picked.join(", ") || "—"}</div>
          <div style={{ fontSize: 13, marginBottom: 4 }}>Schedule: {startDate} → {endDate}</div>
          <div style={{ fontSize: 13, marginBottom: 4 }}>Daily budget: ${dailyBudget} · Total: ${totalBudget}</div>
          <div style={{ fontSize: 13, marginBottom: 4 }}>Targeting: {JSON.stringify(targeting)}</div>
          <div style={{ fontSize: 13, marginBottom: 12 }}>Click URL: {clickUrl}</div>
          <div style={{ color: "#9aa3af", fontSize: 12 }}>
            Clicking checkout opens Stripe test mode. After payment, your campaign
            enters admin moderation. You can pause anytime.
          </div>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 24 }}>
        {step > 0 ? <button data-testid="buy-back" onClick={() => setStep(s => s - 1)} style={btnS}>
                      <ChevronLeft size={14} /> Back</button> : <span />}
        {step < 4
          ? <button data-testid="buy-next"
                    onClick={() => setStep(s => s + 1)}
                    disabled={(step === 0 && picked.length === 0)
                                || (step === 1 && (!creativeUrl || !clickUrl))}
                    style={btnP}>Next <ChevronRight size={14} /></button>
          : <button data-testid="buy-submit" onClick={submit} disabled={busy} style={btnP}>
              {busy ? "Processing…" : "Pay & submit"} <Check size={14} />
            </button>}
      </div>
    </div>
  );
}


export function MyBannerCampaigns() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/ads/advertiser/banner-campaigns`,
        { withCredentials: true });
      setItems(r.data?.items || []);
    } catch (_) { setItems([]); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const pauseToggle = async (c) => {
    const next = c.status === "active" ? "paused" : "active";
    try {
      await axios.patch(`${API}/ads/advertiser/banner-campaigns/${c.campaign_id}`,
        { status: next }, { withCredentials: true });
      load();
    } catch (_) {}
  };

  return (
    <div data-testid="my-campaigns-page"
         style={{ maxWidth: 1080, margin: "0 auto", padding: 24, color: "#fff" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                     marginBottom: 22 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, margin: 0 }}>My Banner Campaigns</h1>
        <Link to="/advertiser/banner/buy" data-testid="my-campaigns-new"
              style={{ ...btnP, textDecoration: "none" }}>+ New Campaign</Link>
      </div>
      {loading ? <div style={{ color: "#9aa3af" }}>Loading…</div>
       : items.length === 0 ? <div data-testid="my-campaigns-empty"
                                    style={{ color: "#9aa3af", padding: 24, textAlign: "center" }}>
              No campaigns yet. Click <Link to="/advertiser/banner/buy" style={{color:"#00d9ff"}}>+ New Campaign</Link>.
            </div>
       : <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
           <thead style={{ color: "#9aa3af", fontSize: 11, fontFamily: "monospace", letterSpacing: 1 }}>
             <tr><th align="left" style={{ padding: 8 }}>SLOT(S)</th>
                 <th align="left" style={{ padding: 8 }}>STATUS</th>
                 <th align="right" style={{ padding: 8 }}>IMPR</th>
                 <th align="right" style={{ padding: 8 }}>CLICKS</th>
                 <th align="right" style={{ padding: 8 }}>CTR</th>
                 <th align="right" style={{ padding: 8 }}>BUDGET</th>
                 <th align="center" style={{ padding: 8 }}></th></tr>
           </thead>
           <tbody>
             {items.map(c => (
               <tr key={c.campaign_id} data-testid={`campaign-row-${c.campaign_id}`}
                   style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                 <td style={{ padding: 8 }}>{(c.slot_keys || []).join(", ")}</td>
                 <td style={{ padding: 8 }}>
                   <span style={{ padding: "2px 8px", borderRadius: 10, fontSize: 11,
                                    background: c.status === "active" ? "rgba(34,197,94,0.15)"
                                                : c.status === "paused" ? "rgba(245,158,11,0.15)"
                                                : "rgba(148,163,184,0.15)",
                                    color: c.status === "active" ? "#22c55e"
                                                : c.status === "paused" ? "#f59e0b"
                                                : "#94a3b8" }}>{c.status}</span>
                 </td>
                 <td align="right" style={{ padding: 8 }}>{c.impressions || 0}</td>
                 <td align="right" style={{ padding: 8 }}>{c.clicks || 0}</td>
                 <td align="right" style={{ padding: 8 }}>{((c.ctr || 0) * 100).toFixed(2)}%</td>
                 <td align="right" style={{ padding: 8 }}>${(c.total_budget || 0).toFixed(2)}</td>
                 <td align="center" style={{ padding: 8 }}>
                   {(c.status === "active" || c.status === "paused") && (
                     <button data-testid={`pause-${c.campaign_id}`}
                             onClick={() => pauseToggle(c)} style={{ ...btnS, padding: "4px 10px" }}>
                       {c.status === "active" ? "Pause" : "Resume"}
                     </button>
                   )}
                 </td>
               </tr>
             ))}
           </tbody>
         </table>}
    </div>
  );
}


export default BuyBannerSlot;
