// P1.4 — Web Picture-in-Picture video player for video podcasts.
// A floating overlay that plays an episode's video and can pop out into the
// browser's native Picture-in-Picture window so playback continues while the
// listener browses the rest of the app. Uses the standard
// HTMLVideoElement.requestPictureInPicture() API (Chromium/Safari).
import { useEffect, useRef, useState } from "react";
import { X, PictureInPicture2, Loader2 } from "lucide-react";

export default function PipVideoPlayer({ videoUrl, title, onClose }) {
  const videoRef = useRef(null);
  const [pipActive, setPipActive] = useState(false);
  const [error, setError] = useState(null);
  const supported = typeof document !== "undefined" && document.pictureInPictureEnabled;

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return undefined;
    const onEnter = () => setPipActive(true);
    const onLeave = () => setPipActive(false);
    v.addEventListener("enterpictureinpicture", onEnter);
    v.addEventListener("leavepictureinpicture", onLeave);
    return () => {
      v.removeEventListener("enterpictureinpicture", onEnter);
      v.removeEventListener("leavepictureinpicture", onLeave);
    };
  }, []);

  const togglePip = async () => {
    const v = videoRef.current;
    if (!v) return;
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture();
      } else {
        await v.requestPictureInPicture();
      }
    } catch (e) {
      setError("Picture-in-Picture isn't available in this browser.");
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/80 p-4"
         data-testid="pip-video-overlay" onClick={onClose}>
      <div className="bg-slate-950 rounded-2xl overflow-hidden max-w-2xl w-full border border-white/10"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <div className="text-sm font-black text-white truncate pr-3" data-testid="pip-video-title">
            {title || "Video podcast"}
          </div>
          <button onClick={onClose} data-testid="pip-video-close"
                  className="text-white/60 hover:text-white shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>
        <video
          ref={videoRef}
          src={videoUrl}
          controls
          autoPlay
          playsInline
          data-testid="pip-video-el"
          className="w-full aspect-video bg-black"
        />
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <div className="text-xs text-white/50">
            {pipActive ? "Playing in a floating window — keep browsing." : "Pop out to keep watching while you browse."}
          </div>
          <button
            onClick={togglePip}
            disabled={!supported}
            data-testid="pip-video-toggle"
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-black transition ${
              supported ? "bg-violet-600 text-white hover:bg-violet-500" : "bg-white/10 text-white/40 cursor-not-allowed"}`}>
            <PictureInPicture2 className="w-4 h-4" />
            {pipActive ? "Exit PiP" : "Picture-in-Picture"}
          </button>
        </div>
        {error && <div className="px-4 pb-3 text-xs text-red-400" data-testid="pip-video-error">{error}</div>}
        {!supported && (
          <div className="px-4 pb-3 text-xs text-amber-400" data-testid="pip-video-unsupported">
            This browser doesn't support Picture-in-Picture.
          </div>
        )}
      </div>
    </div>
  );
}

// Small helper to fetch an episode's media + open the player. Returns a
// loader-aware trigger the caller renders per episode.
export function useEpisodeVideo(apiBase) {
  const [videoEp, setVideoEp] = useState(null);   // {videoUrl, title}
  const [loadingId, setLoadingId] = useState(null);

  const open = async (episode, axiosInstance, onAudioOnly) => {
    setLoadingId(episode.id);
    try {
      const r = await axiosInstance.get(`${apiBase}/podcasts/episodes/${episode.id}/media`);
      const url = r.data?.video_url;
      if (url) {
        setVideoEp({ videoUrl: url, title: episode.title });
      } else if (onAudioOnly) {
        onAudioOnly();
      }
    } catch (e) {
      if (onAudioOnly) onAudioOnly();
    } finally { setLoadingId(null); }
  };

  return { videoEp, setVideoEp, loadingId, open, LoaderIcon: Loader2 };
}
