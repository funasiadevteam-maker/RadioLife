// A single mixed-feed card. Type-aware media + CTA; reuses the real feed item
// shape from GET /api/social/feed-v2.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Heart, MessageCircle, Share2, MoreHorizontal, Play, BadgeCheck, Radio, Bookmark,
} from "lucide-react";
import { timeAgo, ctaTo, initials } from "./sfTheme";

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
};

export default function SocialFeedCard({ item, t, onFollow }) {
  const nav = useNavigate();
  const actor = item.actor || {};
  const meta = item.meta || {};
  const cta = item.cta;
  const badge = BADGE[item.type];
  const [liked, setLiked] = useState(false);
  const [likes, setLikes] = useState(meta.like_count ?? 0);
  const [saved, setSaved] = useState(false);
  const [followed, setFollowed] = useState(item.follow_relationship === "following");

  const log = (event) => {
    axios.post(`${API}/social/feed-events`, { event, item_id: item.id, item_type: item.type },
      { withCredentials: true }).catch(() => {});
  };
  const like = () => { setLiked((v) => !v); setLikes((n) => (liked ? n - 1 : n + 1)); log("feed_like"); };
  const openCta = () => { log("feed_item_open"); nav(ctaTo(cta)); };
  const follow = () => { setFollowed(true); onFollow && onFollow(actor.id); log("feed_follow_click"); };

  const products = meta.products || [];

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
            <span>{timeAgo(item.created_at)}</span>
            {item.ranking_reason && <span>· {item.ranking_reason}</span>}
          </div>
        </div>
        {!followed && actor.id && actor.kind !== "self" && (
          <button onClick={follow} data-testid="sf-card-follow" className="sf-press"
            style={{ fontSize: 12, fontWeight: 800, color: t.accent, background: t.accentSoft, border: "none", borderRadius: 999, padding: "6px 14px", cursor: "pointer" }}>
            Follow
          </button>
        )}
        <button className="sf-press" style={{ background: "none", border: "none", color: t.muted, cursor: "pointer", padding: 4 }}><MoreHorizontal size={18} /></button>
      </div>

      {/* text */}
      {(item.title || item.text) && (
        <div style={{ padding: "0 14px 10px" }}>
          {item.title && <div style={{ fontWeight: 800, fontSize: 15, color: t.text, marginBottom: 2 }}>{item.title}</div>}
          {item.text && <div className="sf-clamp3" style={{ fontSize: 14, color: t.text2, lineHeight: 1.45 }}>{item.text}</div>}
        </div>
      )}

      {/* media */}
      {item.media_url && (
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
        <FooterBtn t={t} icon={Share2} label="Share" onClick={() => log("feed_share")} testid="sf-share" />
        <FooterBtn t={t} active={saved} activeColor={t.accent} icon={Bookmark} label="" onClick={() => { setSaved((v) => !v); log("feed_save"); }} testid="sf-save" />
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
