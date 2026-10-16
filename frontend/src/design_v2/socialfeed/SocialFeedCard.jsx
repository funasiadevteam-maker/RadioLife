// A single mixed-feed card. Type-aware media + CTA; reuses the real feed item
// shape from GET /api/social/feed-v2.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Heart, MessageCircle, Share2, MoreHorizontal, Play, BadgeCheck, Radio, Bookmark,
} from "lucide-react";
import { timeAgo, ctaTo, initials } from "./sfTheme";
import { RadioClipPlayer, ClipShareModal } from "./RadioClip";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const BADGE = {
  LIVE_VIDEO: { label: "LIVE", live: true },
  BUSINESS_LIVE: { label: "LIVE", live: true },
  LIVE_RADIO: { label: "LIVE", live: true },
  DREAM: { label: "DREAM" },
  TAROT_SHARE: { label: "TAROT" },
  EVENT: { label: "EVENT" },
  GAME: { label: "PLAY" },
  CLUB_POST: { label: "CLUB" },
  OFFER: { label: "OFFER" },
  RADIO_CLIP: { label: "CLIP" },
};

export default function SocialFeedCard({ item, t, onFollow }) {
  const nav = useNavigate();
  const actor = item.actor || {};
  const meta = item.meta || {};
  const cta = item.cta;
  const badge = BADGE[item.type];
  const isMine = !!item.is_mine || actor.kind === "self";
  const pending = !!item.approval_status && item.approval_status !== "approved";
  const [liked, setLiked] = useState(!!meta.liked_by_me);
  const [likes, setLikes] = useState(meta.like_count ?? 0);
  const [saved, setSaved] = useState(!!meta.saved_by_me);
  const [shares, setShares] = useState(meta.share_count ?? 0);
  const [followed, setFollowed] = useState(
    item.follow_relationship === "following" || item.follow_relationship === "friend_following");
  const [clipOpen, setClipOpen] = useState(false);

  const log = (event) => {
    axios.post(`${API}/social/feed-events`, { event, item_id: item.id, item_type: item.type },
      { withCredentials: true }).catch(() => {});
  };

  // Real like — optimistic, reconciled with the server, reverts on failure.
  const like = async () => {
    const next = !liked;
    setLiked(next); setLikes((n) => Math.max(0, n + (next ? 1 : -1)));
    try {
      const r = await axios.post(`${API}/social/wall/like`, { item_id: item.id }, { withCredentials: true });
      if (r.data) { setLiked(!!r.data.liked); if (typeof r.data.like_count === "number") setLikes(r.data.like_count); }
      log("feed_like");
    } catch (_e) { setLiked(!next); setLikes((n) => Math.max(0, n + (next ? -1 : 1))); }
  };
  const save = async () => {
    const next = !saved; setSaved(next);
    try {
      const r = await axios.post(`${API}/social/wall/save`, { item_id: item.id }, { withCredentials: true });
      if (r.data) setSaved(!!r.data.saved);
      log("feed_save");
    } catch (_e) { setSaved(!next); }
  };
  const share = async () => {
    try {
      const r = await axios.post(`${API}/social/wall/share`, { item_id: item.id }, { withCredentials: true });
      if (r.data && typeof r.data.share_count === "number") setShares(r.data.share_count);
    } catch (_e) { /* best-effort counter */ }
    try {
      const url = window.location.origin + ctaTo(cta);
      if (navigator.share) await navigator.share({ title: actor.name || "FUUSIC", url });
      else if (navigator.clipboard) await navigator.clipboard.writeText(url);
    } catch (_e) { /* user dismissed */ }
    log("feed_share");
  };
  const openCta = () => { log("feed_item_open"); nav(ctaTo(cta)); };
  const follow = () => { setFollowed(true); onFollow && onFollow(actor.id); log("feed_follow_click"); };

  const products = meta.products || [];
  const isSponsored = !!item.sponsored || item.type === "SPONSORED_POST";
  const isReading = item.type === "READING";
  const [hidden, setHidden] = useState(false);
  const hideAd = async () => {
    setHidden(true);
    try {
      const rawId = String(item.id).includes(":") ? item.id.split(":")[1] : item.id;
      await axios.post(`${API}/social/suggestions/dismiss`,
        { actor_type: "sponsored_post", actor_id: rawId, action: "hide" },
        { withCredentials: true });
    } catch (_e) { /* best effort */ }
  };

  if (hidden) return null;

  return (
    <article data-testid={`sf-card-${item.type}`} className="sf-fade-in"
      style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 18, boxShadow: t.shadow, overflow: "hidden" }}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px 8px" }}>
        <Avatar a={actor} t={t} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ fontWeight: 800, fontSize: 14, color: t.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{actor.name || "FUUSIC"}</span>
            {(actor.kind === "business" || actor.verified) && <BadgeCheck size={14} color={t.accent} />}
            {item.type && (item.type.includes("LIVE") || item.type === "BUSINESS_LIVE") && (
              <span style={{ fontSize: 11, color: t.text2 }}>is live</span>
            )}
          </div>
          <div style={{ fontSize: 11.5, color: t.muted, display: "flex", gap: 6, alignItems: "center" }}>
            {isSponsored ? (
              <span data-testid="sf-sponsored-label" style={{ fontWeight: 800, color: t.text2 }}>Sponsored</span>
            ) : isReading ? (
              <span style={{ fontWeight: 700, color: t.accent }}>AI · for reflection</span>
            ) : (
              <>
                <span>{timeAgo(item.created_at)}</span>
                {item.ranking_reason && <span>· {item.ranking_reason}</span>}
              </>
            )}
          </div>
        </div>
        {isMine && pending && (
          <span data-testid="sf-card-pending" style={{ fontSize: 10.5, fontWeight: 800, color: t.gold, background: t.goldBg, border: `1px solid ${t.gold}44`, borderRadius: 999, padding: "4px 10px" }}>
            Pending Review
          </span>
        )}
        {!isSponsored && !isReading && !isMine && !followed && actor.id && actor.kind !== "self" && (
          <button onClick={follow} data-testid="sf-card-follow" className="sf-press"
            style={{ fontSize: 12, fontWeight: 800, color: t.accent, background: t.accentSoft, border: "none", borderRadius: 999, padding: "6px 14px", cursor: "pointer" }}>
            Follow
          </button>
        )}
        {isSponsored ? (
          <button onClick={hideAd} data-testid="sf-hide-ad" className="sf-press"
            style={{ fontSize: 11.5, fontWeight: 700, color: t.muted, background: "none", border: `1px solid ${t.border}`, borderRadius: 999, padding: "5px 11px", cursor: "pointer" }}>
            Hide Ad
          </button>
        ) : (
          <button className="sf-press" style={{ background: "none", border: "none", color: t.muted, cursor: "pointer", padding: 4 }}><MoreHorizontal size={18} /></button>
        )}
      </div>

      {/* text */}
      {(item.title || item.text) && (
        <div style={{ padding: "0 14px 10px" }}>
          {item.title && <div style={{ fontWeight: 800, fontSize: 15, color: t.text, marginBottom: 2 }}>{item.title}</div>}
          {isReading && meta.headline && <div style={{ fontWeight: 700, fontSize: 13.5, color: t.accent, margin: "2px 0 6px" }}>{meta.headline}</div>}
          {item.text && <div className={isReading ? "" : "sf-clamp3"} style={{ fontSize: 14, color: t.text2, lineHeight: 1.45 }}>{item.text}</div>}
          {isReading && meta.disclaimer && (
            <div style={{ marginTop: 8, fontSize: 11, color: t.muted, fontStyle: "italic" }}>{meta.disclaimer}</div>
          )}
        </div>
      )}

      {/* media */}
      {(item.media_type === "audio" || item.media_type === "voice") && item.media_url ? (
        <RadioClipPlayer item={item} t={t} onClip={() => setClipOpen(true)} />
      ) : item.media_url && (
        <div style={{ position: "relative", background: t.cardAlt }}>
          <img src={item.media_url} alt="" loading="lazy"
            style={{ width: "100%", maxHeight: 420, objectFit: "cover", display: "block" }} />
          {badge && (
            <span style={{ position: "absolute", top: 12, left: 12, fontSize: 10.5, fontWeight: 900, letterSpacing: ".06em", color: "#fff", background: badge.live ? t.live : "rgba(0,0,0,.55)", padding: "4px 9px", borderRadius: 999, display: "inline-flex", alignItems: "center", gap: 4 }}>
              {badge.live && <span style={{ width: 6, height: 6, borderRadius: 999, background: "#fff" }} />}{badge.label}
            </span>
          )}
          {(item.media_type === "video" || item.type.includes("LIVE")) && (
            <button onClick={openCta} aria-label="Play" className="sf-press"
              style={{ position: "absolute", inset: 0, margin: "auto", width: 62, height: 62, borderRadius: 999, border: "none", cursor: "pointer", background: "rgba(0,0,0,.45)", display: "grid", placeItems: "center" }}>
              <Play size={26} color="#fff" fill="#fff" />
            </button>
          )}
        </div>
      )}

      {clipOpen && (
        <ClipShareModal t={t} onClose={() => setClipOpen(false)}
          onPosted={() => { setClipOpen(false); log("radio_clip_shared"); }}
          station={{ id: meta.station_id, name: meta.station_name, logo: meta.station_logo,
                     slug: meta.station_slug, show_name: meta.show_name }} />
      )}

      {/* product strip (live commerce) */}
      {products.length > 0 && (
        <div className="sf-noscroll" style={{ display: "flex", gap: 8, overflowX: "auto", padding: "10px 14px 2px" }}>
          {products.slice(0, 4).map((p) => (
            <div key={p.product_id} style={{ flex: "0 0 128px", border: `1px solid ${t.border}`, borderRadius: 12, overflow: "hidden", background: t.cardAlt }}>
              {p.image_url && <img src={p.image_url} alt="" loading="lazy" style={{ width: "100%", height: 72, objectFit: "cover" }} />}
              <div style={{ padding: "6px 8px" }}>
                <div className="sf-clamp2" style={{ fontSize: 11.5, fontWeight: 700, color: t.text }}>{p.title}</div>
                <div style={{ fontSize: 12, fontWeight: 800, color: t.accent }}>{p.offer || (p.price_cents != null ? `$${(p.price_cents / 100).toFixed(0)}` : "")}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* CTA */}
      {cta?.label && (
        <div style={{ padding: "12px 14px 4px" }}>
          <button onClick={openCta} data-testid="sf-card-cta" className="sf-press"
            style={{ width: "100%", padding: "10px", borderRadius: 12, border: "none", cursor: "pointer", fontWeight: 800, fontSize: 13.5, color: "#fff", background: t.accentGrad, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7 }}>
            {(item.type.includes("LIVE") || item.type === "LIVE_RADIO") ? <Radio size={16} /> : null}
            {cta.label}
          </button>
        </div>
      )}

      {/* footer actions */}
      <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "6px 8px 10px", borderTop: `1px solid ${t.border}`, marginTop: 10 }}>
        <FooterBtn t={t} active={liked} activeColor={t.live} icon={Heart} label={likes > 0 ? String(likes) : "Like"} onClick={like} testid="sf-like" />
        <FooterBtn t={t} icon={MessageCircle} label={meta.comment_count ? String(meta.comment_count) : "Comment"} onClick={openCta} testid="sf-comment" />
        <FooterBtn t={t} icon={Share2} label={shares > 0 ? String(shares) : "Share"} onClick={share} testid="sf-share" />
        <FooterBtn t={t} active={saved} activeColor={t.accent} icon={Bookmark} label="" onClick={save} testid="sf-save" />
      </div>
    </article>
  );
}

function Avatar({ a, t }) {
  if (a?.avatar_url) {
    return <img src={a.avatar_url} alt="" loading="lazy" style={{ width: 40, height: 40, borderRadius: 999, objectFit: "cover", flexShrink: 0 }} />;
  }
  return (
    <span style={{ width: 40, height: 40, borderRadius: 999, flexShrink: 0, display: "grid", placeItems: "center", color: "#fff", fontWeight: 800, background: t.accentGrad }}>
      {initials(a?.name)}
    </span>
  );
}

function FooterBtn({ t, icon: Icon, label, onClick, active, activeColor, testid }) {
  return (
    <button onClick={onClick} data-testid={testid} className="sf-press"
      style={{ flex: label ? 1 : "0 0 auto", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "8px 6px", borderRadius: 10, border: "none", background: "transparent", cursor: "pointer", color: active ? activeColor : t.text2, fontWeight: 700, fontSize: 13 }}>
      <Icon size={18} color={active ? activeColor : t.text2} fill={active ? activeColor : "none"} />
      {label && <span>{label}</span>}
    </button>
  );
}
