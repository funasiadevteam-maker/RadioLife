// Share modal — pops up after clicking "Share break". Shows audio preview,
// copy-link button, WhatsApp deep-link, download button.

import { useEffect, useRef, useState } from "react";
import { X, Copy, Download, Share2, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function ShareBreakModal({ share, onClose }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
  // SSR landing path lives under /api/* (per K8s ingress), so crawlers see
  // proper OG meta tags. The same URL auto-redirects real browsers to the SPA.
  const shareUrl = `${BACKEND_URL}${share.share_url}`;
  const directMp3 = `${BACKEND_URL}${share.audio_url}`;

  useEffect(() => () => {
    if (audioRef.current) { try { audioRef.current.pause(); } catch (_e) { /* */ } }
  }, []);

  const toggle = async () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) { try { await a.play(); setPlaying(true); } catch (_e) { /* */ } }
    else { a.pause(); setPlaying(false); }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      toast.success("Link copied!");
    } catch (_e) {
      toast.error("Couldn't copy — long-press the link to copy manually");
    }
  };

  const whatsapp = () => {
    const text = `Sun lo ye banter on FUUSIC 🎙️ ${shareUrl}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
  };

  const download = () => {
    const a = document.createElement("a");
    a.href = directMp3;
    a.download = `bigfm-${share.share_id}.mp3`;
    a.click();
  };

  return (
    <div className="modal-backdrop" data-testid="share-modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-card share-modal-card">
        <button type="button" className="modal-close" onClick={onClose}
                data-testid="share-modal-close" aria-label="Close">
          <X size={16} />
        </button>
        <div className="share-modal-icon"><Share2 size={20} /></div>
        <h3>Share this break</h3>
        <p>
          <b>{share.host_names?.join(" × ") || "RJ"}</b>
          {share.track_title && <> · after "{share.track_title}"</>}
          {share.channel_name && <> on {share.channel_name}</>}
        </p>
        <div className="share-audio-row">
          <button type="button" className={`share-play-btn ${playing ? "is-on" : ""}`}
                  onClick={toggle} data-testid="share-modal-play">
            {playing ? "❚❚" : "▶"}
          </button>
          <div className="share-meta">
            <div className="share-bar"><div className="share-bar-fill" /></div>
            <div className="share-dur mono">~{Math.round(share.duration_sec)}s · MP3</div>
          </div>
        </div>
        <audio ref={audioRef} src={directMp3} preload="auto"
               onEnded={() => setPlaying(false)} />
        <div className="share-link-row">
          <input className="share-link-input" value={shareUrl} readOnly
                 data-testid="share-modal-link-input" />
          <button type="button" className="modal-btn ghost" onClick={copy}
                  data-testid="share-modal-copy">
            <Copy size={13} /> Copy
          </button>
        </div>
        <div className="share-actions">
          <button type="button" className="share-action wa" onClick={whatsapp}
                  data-testid="share-modal-whatsapp">
            <Share2 size={14} /> WhatsApp
          </button>
          <button type="button" className="share-action dl" onClick={download}
                  data-testid="share-modal-download">
            <Download size={14} /> Download MP3
          </button>
        </div>
        <p className="share-foot mono">
          <CheckCircle2 size={11} /> SHARED · Public link, anyone with it can listen
        </p>
      </div>
    </div>
  );
}
