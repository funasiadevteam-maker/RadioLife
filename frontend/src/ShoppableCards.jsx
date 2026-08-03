// Phase 36d Turn 2 — Shoppable cards: creator form + listener sidebar widget.
//
// Exports:
//   <ShoppableCardsCreator episodeId? magicClipId? />  — creator side
//   <ShoppableCardsSidebar episodeId? magicClipId? variant />  — listener side
//
// Click-proxy: tiles render as anchor tags pointing to
// `${API}/podcasts/shoppable-cards/${id}/click`. The browser follows the 302
// to the actual product URL. The proxy records an analytics row first.

import React, {useEffect, useState, useCallback} from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
axios.defaults.withCredentials = true;

const DESCRIPTION_MAX = 280;
const PRODUCT_URL_MAX = 1000;

function formatPrice(cents, currency) {
  if (cents == null) return "";
  const dollars = (cents / 100).toFixed(2);
  return `${currency || "USD"} ${dollars}`;
}


export function ShoppableCardsCreator({episodeId, magicClipId, isOwner = true}) {
  const [items, setItems] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [err, setErr] = useState("");

  const url = episodeId
    ? `${API}/podcasts/episodes/${episodeId}/shoppable-cards`
    : `${API}/podcasts/magic-clips/${magicClipId}/shoppable-cards`;

  const refresh = useCallback(async () => {
    try {
      const r = await axios.get(`${url}?include_inactive=true`);
      setItems(r.data?.items || []);
    } catch (e) { setErr(e?.response?.data?.detail || e.message); }
  }, [url]);

  useEffect(() => { refresh(); }, [refresh]);

  const onDelete = async (c) => {
    if (!window.confirm("Soft-delete this card?")) return;
    await axios.delete(`${API}/podcasts/shoppable-cards/${c.id}`);
    refresh();
  };

  return (
    <div data-testid="shoppable-cards-creator" style={{color: "#e7e7ea"}}>
      <div style={{display: "flex", justifyContent: "space-between",
                          alignItems: "center", marginBottom: 12}}>
        <h2 style={{fontSize: 18, margin: 0}}>Shoppable cards</h2>
        {isOwner && (
          <button data-testid="shoppable-add-btn"
                          onClick={() => setShowForm(true)} style={btnPrimary()}>
            + Add card
          </button>
        )}
      </div>
      {err && <div data-testid="shoppable-err"
                            style={{color: "#ef4444", fontSize: 12, marginBottom: 8}}>
                {String(err)}</div>}
      {items.length === 0 && !showForm && (
        <div data-testid="shoppable-empty"
                style={{padding: 16, textAlign: "center", color: "#9aa3af",
                            fontSize: 13}}>
          No cards yet — link a product to monetize this {episodeId ? "episode" : "clip"}.
        </div>
      )}
      {items.map((c) => (
        <div key={c.id} data-testid={`shoppable-row-${c.id}`}
                data-active={String(!!c.active)}
                style={rowStyle(c.active)}>
          <div style={{width: 56, height: 56, borderRadius: 6,
                              flexShrink: 0, overflow: "hidden",
                              background: c.image_url
                                                  ? `center/cover url(${c.image_url})`
                                                  : "linear-gradient(135deg,#1e1e2a,#2a1a2e)"}} />
          <div style={{flex: 1, minWidth: 0}}>
            <div style={{fontWeight: 600, fontSize: 14}}>
              {c.title}{!c.active && (
                <span data-testid={`shoppable-deleted-${c.id}`}
                          style={{marginLeft: 8, fontSize: 10, color: "#9aa3af"}}>
                  (deleted)
                </span>
              )}
            </div>
            <div style={{fontSize: 11, color: "#9aa3af"}}>
              {formatPrice(c.price_cents, c.currency)} · order {c.display_order}
              {c.product_url && (
                <> · <a href={c.product_url} target="_blank" rel="noreferrer"
                                    style={{color: "#f59e0b"}}>{shortUrl(c.product_url)}</a></>
              )}
            </div>
            {c.description && (
              <div style={{fontSize: 12, color: "#9aa3af", marginTop: 2,
                                  lineHeight: 1.4}}>{c.description}</div>
            )}
          </div>
          {isOwner && c.active && (
            <button data-testid={`shoppable-del-${c.id}`}
                            onClick={() => onDelete(c)} style={btnDelete()}>
              Delete
            </button>
          )}
        </div>
      ))}
      {showForm && (
        <ShoppableCardForm
          url={url}
          onClose={() => setShowForm(false)}
          onCreated={() => { setShowForm(false); refresh(); }} />
      )}
    </div>
  );
}


function ShoppableCardForm({url, onClose, onCreated}) {
  const [title, setTitle]     = useState("");
  const [productUrl, setProductUrl] = useState("");
  const [priceDollars, setPriceDollars] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [description, setDescription] = useState("");
  const [displayOrder, setDisplayOrder] = useState(0);
  const [file, setFile]   = useState(null);
  const [busy, setBusy]   = useState(false);
  const [err, setErr]     = useState("");

  const submit = async (e) => {
    e?.preventDefault?.();
    setBusy(true); setErr("");
    try {
      const fd = new FormData();
      fd.append("title", title);
      fd.append("product_url", productUrl);
      if (priceDollars.trim()) {
        const cents = Math.round(parseFloat(priceDollars) * 100);
        fd.append("price_cents", String(cents));
      }
      fd.append("currency", currency);
      fd.append("description", description);
      fd.append("display_order", String(displayOrder));
      if (file) fd.append("image", file);
      await axios.post(url, fd, {headers: {"Content-Type": "multipart/form-data"}});
      onCreated();
    } catch (e) { setErr(e?.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  };

  return (
    <div data-testid="shoppable-form-modal"
            style={{position: "fixed", inset: 0, zIndex: 60,
                        background: "rgba(0,0,0,0.7)",
                        display: "flex", alignItems: "center",
                        justifyContent: "center"}}
            onClick={onClose}>
      <form data-testid="shoppable-form"
                  onSubmit={submit}
                  onClick={(e) => e.stopPropagation()}
                  style={{background: "#13131a", padding: 24,
                              borderRadius: 12, maxWidth: 480, width: "92%",
                              maxHeight: "85vh", overflow: "auto",
                              border: "1px solid rgba(255,255,255,0.06)"}}>
        <h3 style={{fontSize: 18, fontWeight: 700, margin: 0,
                            marginBottom: 12}}>New shoppable card</h3>
        <Field label="Title">
          <input data-testid="sh-title" value={title} required
                      onChange={(e) => setTitle(e.target.value)}
                      maxLength={120} style={inp()} />
        </Field>
        <Field label="Product URL">
          <input data-testid="sh-url" value={productUrl} required type="url"
                      onChange={(e) => setProductUrl(e.target.value)}
                      maxLength={PRODUCT_URL_MAX} style={inp()}
                      placeholder="https://…" />
        </Field>
        <div style={{display: "flex", gap: 8}}>
          <Field label="Price">
            <input data-testid="sh-price" value={priceDollars} type="number"
                        step="0.01" min="0"
                        onChange={(e) => setPriceDollars(e.target.value)}
                        style={inp()} placeholder="29.99" />
          </Field>
          <Field label="Currency">
            <select data-testid="sh-currency" value={currency}
                          onChange={(e) => setCurrency(e.target.value)}
                          style={inp()}>
              {["USD","EUR","GBP","AED","INR"].map(c => (
                <option key={c} value={c}>{c}</option>))}
            </select>
          </Field>
        </div>
        <Field label={`Description (${description.length}/${DESCRIPTION_MAX})`}>
          <textarea data-testid="sh-desc" value={description}
                            onChange={(e) => setDescription(
                              e.target.value.slice(0, DESCRIPTION_MAX))}
                            style={{...inp(), minHeight: 60, resize: "vertical"}} />
        </Field>
        <Field label="Display order">
          <input data-testid="sh-order" value={displayOrder} type="number"
                      onChange={(e) => setDisplayOrder(Number(e.target.value))}
                      style={inp()} />
        </Field>
        <Field label="Image (optional · png/jpg/webp · max 1.5MB)">
          <input data-testid="sh-image" type="file"
                      accept="image/png,image/jpeg,image/webp,image/gif"
                      onChange={(e) => setFile(e.target.files?.[0] || null)}
                      style={{fontSize: 12, color: "#9aa3af"}} />
        </Field>
        {err && <div data-testid="sh-form-err"
                              style={{color: "#ef4444", fontSize: 12, marginTop: 6}}>
                  {String(err)}</div>}
        <div style={{display: "flex", gap: 8, marginTop: 12,
                            justifyContent: "flex-end"}}>
          <button type="button" onClick={onClose}
                          data-testid="sh-form-cancel" style={btnSec()}>
            Cancel
          </button>
          <button type="submit" disabled={busy || !title || !productUrl}
                          data-testid="sh-form-submit"
                          style={btnPrimary(busy || !title || !productUrl)}>
            {busy ? "Saving…" : "Save card"}
          </button>
        </div>
      </form>
    </div>
  );
}


export function ShoppableCardsSidebar({episodeId, magicClipId,
                                                                          variant = "full"}) {
  const [items, setItems] = useState([]);
  const [showAll, setShowAll] = useState(false);

  const url = episodeId
    ? `${API}/podcasts/episodes/${episodeId}/shoppable-cards`
    : `${API}/podcasts/magic-clips/${magicClipId}/shoppable-cards`;

  useEffect(() => {
    axios.get(url).then((r) => setItems(r.data?.items || []))
                          .catch(() => setItems([]));
  }, [url]);

  if (items.length === 0) return null;
  const visible = showAll ? items : items.slice(0, 3);
  const isCompact = variant === "compact";

  return (
    <aside data-testid="shoppable-sidebar"
                data-variant={variant}
                style={{background: "#101018", padding: 14,
                            borderRadius: 10,
                            border: "1px solid rgba(255,255,255,0.06)"}}>
      <div style={{fontSize: 11, color: "#9aa3af",
                          textTransform: "uppercase", letterSpacing: 0.5,
                          marginBottom: 10}}>
        Shop the {episodeId ? "episode" : "clip"}
      </div>
      <div data-testid="shoppable-grid"
              style={{display: "grid",
                          gridTemplateColumns: isCompact
                              ? "repeat(2, minmax(0, 1fr))" : "1fr",
                          gap: 8}}>
        {visible.map((c) => (
          <a key={c.id} data-testid={`shoppable-tile-${c.id}`}
              href={`${API}/podcasts/shoppable-cards/${c.id}/click`}
              target="_blank" rel="noreferrer sponsored"
              style={{display: "flex", gap: 8, textDecoration: "none",
                          padding: 8, borderRadius: 6, color: "#e7e7ea",
                          background: "rgba(255,255,255,0.02)",
                          border: "1px solid rgba(255,255,255,0.04)"}}>
            <div style={{width: 56, height: 56, borderRadius: 4,
                                flexShrink: 0, overflow: "hidden",
                                background: c.image_url
                                                    ? `center/cover url(${c.image_url})`
                                                    : "linear-gradient(135deg,#1e1e2a,#2a1a2e)"}} />
            <div style={{flex: 1, minWidth: 0}}>
              <div style={{fontWeight: 600, fontSize: 12,
                                  overflow: "hidden", textOverflow: "ellipsis",
                                  whiteSpace: "nowrap"}}>{c.title}</div>
              {c.price_cents != null && (
                <div style={{fontSize: 11, color: "#f59e0b", marginTop: 2}}>
                  {formatPrice(c.price_cents, c.currency)}
                </div>
              )}
              {!isCompact && c.description && (
                <div style={{fontSize: 11, color: "#9aa3af",
                                    marginTop: 2, lineHeight: 1.3,
                                    overflow: "hidden", textOverflow: "ellipsis",
                                    display: "-webkit-box",
                                    WebkitLineClamp: 2,
                                    WebkitBoxOrient: "vertical"}}>
                  {c.description}
                </div>
              )}
            </div>
          </a>
        ))}
      </div>
      {items.length > 3 && (
        <button data-testid="shoppable-show-all"
                        onClick={() => setShowAll(!showAll)}
                        style={{marginTop: 8, ...btnSec()}}>
          {showAll ? "Show fewer" : `Show all (${items.length})`}
        </button>
      )}
    </aside>
  );
}


function Field({label, children}) {
  return (
    <div style={{marginBottom: 10, flex: 1}}>
      <div style={{fontSize: 10, textTransform: "uppercase",
                            color: "#9aa3af", letterSpacing: 0.5, marginBottom: 4}}>
        {label}
      </div>
      {children}
    </div>
  );
}


const rowStyle = (active) => ({
  display: "flex", gap: 12, padding: 10, marginBottom: 6,
  borderRadius: 8, background: "#101018",
  border: "1px solid rgba(255,255,255,0.06)",
  opacity: active ? 1 : 0.4,
});
const inp = () => ({width: "100%", padding: 8, borderRadius: 6,
  background: "#0a0a0c", color: "#e7e7ea",
  border: "1px solid rgba(255,255,255,0.1)", fontSize: 13});
const btnPrimary = (disabled) => ({padding: "6px 14px", borderRadius: 6,
  fontSize: 12, fontWeight: 700, cursor: disabled ? "not-allowed" : "pointer",
  background: disabled ? "#3f3f46" : "#f59e0b",
  color: disabled ? "#a1a1aa" : "#0a0a0c", border: "none"});
const btnSec = () => ({padding: "6px 12px", borderRadius: 6, fontSize: 11,
  fontWeight: 700, cursor: "pointer",
  background: "rgba(255,255,255,0.05)", color: "#e7e7ea",
  border: "1px solid rgba(255,255,255,0.1)"});
const btnDelete = () => ({...btnSec(), color: "#ef4444"});

function shortUrl(u) {
  try { return new URL(u).host; } catch { return (u || "").slice(0, 30); }
}
