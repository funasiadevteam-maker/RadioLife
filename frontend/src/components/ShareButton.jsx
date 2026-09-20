/** Phase 42-E2.2 — Universal share button.
 *  Web Share API first.  On platforms without it (older desktop
 *  browsers), opens a popover with explicit per-channel buttons +
 *  Copy Link.  Every successful invocation POSTs to /api/share/log
 *  so the backend awards points and tracks the event.
 */
import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import { Share2, Copy, X, Mail, Send, Link as LinkIcon } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/AuthContext";

function _buildShareUrl(passed) {
  if (passed) return passed;
  if (typeof window !== "undefined" && window.location) {
    return window.location.href;
  }
  return "";
}

async function _logShare({ featureType, contentId, channel, url }) {
  try {
    await axios.post(`${API}/share/log`, {
      feature_type: featureType || "other",
      content_id:    contentId || null,
      channel:        channel || "other",
      url:                url || null,
    }, { withCredentials: true });
  } catch (e) { /* silent — analytics only */ }
}

export default function ShareButton({
  title, text, url, featureType, contentId,
  compact = false, className = "", iconSize = 14,
}) {
  const shareUrl = _buildShareUrl(url);
  const shareText = text || title || "Check out FUUSIC";
  const shareTitle = title || "FUUSIC";
  const [open, setOpen] = useState(false);
  const popRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (popRef.current && !popRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  const tryNativeShare = async () => {
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ title: shareTitle, text: shareText, url: shareUrl });
        _logShare({ featureType, contentId, channel: "native", url: shareUrl });
        return true;
      } catch (_e) {
        return false;   // user cancelled or share API rejected
      }
    }
    return false;
  };

  const onMainClick = async (e) => {
    e.stopPropagation();
    e.preventDefault();
    const native = await tryNativeShare();
    if (!native) {
      setOpen((v) => !v);
    }
  };

  const channelLink = (channel) => {
    const t = encodeURIComponent(shareText);
    const u = encodeURIComponent(shareUrl);
    switch (channel) {
      case "whatsapp":  return `https://wa.me/?text=${t}%20${u}`;
      case "twitter":    return `https://twitter.com/intent/tweet?text=${t}&url=${u}`;
      case "facebook":  return `https://www.facebook.com/sharer/sharer.php?u=${u}`;
      case "linkedin":  return `https://www.linkedin.com/sharing/share-offsite/?url=${u}`;
      case "telegram":  return `https://t.me/share/url?url=${u}&text=${t}`;
      case "email":      return `mailto:?subject=${encodeURIComponent(shareTitle)}&body=${t}%0A%0A${u}`;
      default:              return shareUrl;
    }
  };

  const onChannelClick = async (channel) => {
    if (channel === "copy_link") {
      try {
        await navigator.clipboard.writeText(shareUrl);
        toast.success("Link copied");
      } catch {
        toast.error("Couldn't copy");
      }
      _logShare({ featureType, contentId, channel, url: shareUrl });
    } else {
      window.open(channelLink(channel), "_blank", "noopener,noreferrer");
      _logShare({ featureType, contentId, channel, url: shareUrl });
    }
    setOpen(false);
  };

  return (
    <div className={`relative inline-block ${className}`}>
      <button
        type="button"
        data-testid={featureType
          ? `share-btn-${featureType}${contentId ? `-${contentId}` : ""}`
          : "share-btn"}
        data-feature-type={featureType || "other"}
        onClick={onMainClick}
        className={compact
          ? "inline-flex items-center justify-center w-8 h-8 rounded-full hover:bg-white/[0.08] text-white/70 hover:text-white transition-colors"
          : "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-white/[0.1] text-xs text-white/80 hover:bg-white/[0.05] transition-colors"}
        title="Share"
        aria-label="Share">
        <Share2 size={iconSize} />
        {!compact && <span>Share</span>}
      </button>

      {open && (
        <div
          ref={popRef}
          data-testid="share-popover"
          className="absolute right-0 bottom-full mb-2 z-50
                                  min-w-[200px] rounded-xl border border-white/[0.08]
                                  bg-[#0f0f12] p-2 shadow-xl"
          onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between px-2 pb-1.5
                                          text-[10px] font-mono uppercase tracking-widest
                                          text-white/40">
            Share via
            <button type="button"
                            data-testid="share-popover-close"
                            onClick={() => setOpen(false)}
                            className="text-white/30 hover:text-white/60">
              <X size={11} />
            </button>
          </div>
          <ul className="text-sm">
            <ChannelRow channel="copy_link"  label="Copy link"  icon={<LinkIcon size={13} />} onClick={onChannelClick} />
            <ChannelRow channel="whatsapp"  label="WhatsApp"    icon={<Send size={13} />}        onClick={onChannelClick} />
            <ChannelRow channel="twitter"    label="Twitter / X" icon={<Share2 size={13} />}    onClick={onChannelClick} />
            <ChannelRow channel="facebook"  label="Facebook"    icon={<Share2 size={13} />}    onClick={onChannelClick} />
            <ChannelRow channel="linkedin"  label="LinkedIn"    icon={<Share2 size={13} />}    onClick={onChannelClick} />
            <ChannelRow channel="email"      label="Email"          icon={<Mail size={13} />}        onClick={onChannelClick} />
          </ul>
        </div>
      )}
    </div>
  );
}

function ChannelRow({ channel, label, icon, onClick }) {
  return (
    <li>
      <button
        type="button"
        data-testid={`share-channel-${channel}`}
        onClick={() => onClick(channel)}
        className="w-full text-left flex items-center gap-2 px-2 py-1.5
                                  rounded-md text-white/80 hover:bg-white/[0.06] hover:text-white">
        {icon}
        <span>{label}</span>
      </button>
    </li>
  );
}
