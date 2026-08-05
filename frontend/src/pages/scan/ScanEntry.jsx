// Phase AD.7 — /scan entry page.  Opens the camera, decodes QR codes,
// and navigates to /scan-to-pay/{token} on a successful scan.  Reuses
// the same BarcodeDetector + html5-qrcode fallback pattern as VenueOffers.
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { QrCode, Camera, AlertTriangle, ArrowLeft, Keyboard } from "lucide-react";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const SCAN_URL_RE = /\/scan-to-pay\/(stq_[a-zA-Z0-9_-]+)/;

export default function ScanEntry() {
  const nav = useNavigate();
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const videoRef = useRef(null);
  const intervalRef = useRef(null);
  const scannerRef = useRef(null);
  const streamRef = useRef(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState(null);
  const [manualToken, setManualToken] = useState("");

  const cleanup = () => {
    if (intervalRef.current) { clearInterval(intervalRef.current);
                                                          intervalRef.current = null; }
    if (scannerRef.current) {
      try { scannerRef.current.stop(); } catch (_e) { /* */ }
      scannerRef.current = null;
    }
    if (streamRef.current) {
      try { streamRef.current.getTracks().forEach((t) => t.stop()); }
      catch (_e) { /* */ }
      streamRef.current = null;
    }
  };

  useEffect(() => cleanup, []);

  const handleDecoded = (raw) => {
    if (!raw) return;
    // QR may hold either a full URL or just the token.
    const m = String(raw).match(SCAN_URL_RE);
    const token = m ? m[1] : (raw.startsWith("stq_") ? raw : null);
    if (!token) {
      setError("Not a RadioLife scan-to-pay QR.");
      return;
    }
    cleanup();
    setScanning(false);
    nav(`/scan-to-pay/${token}`);
  };

  const startScan = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" }});
      streamRef.current = stream;
      const v = videoRef.current;
      v.srcObject = stream; await v.play();
      setScanning(true);
      // Try BarcodeDetector, fall back to html5-qrcode.
      const Detector = (typeof window !== "undefined"
                                            && "BarcodeDetector" in window)
        ? new window.BarcodeDetector({ formats: ["qr_code"] }) : null;
      if (Detector) {
        intervalRef.current = setInterval(async () => {
          try {
            const codes = await Detector.detect(v);
            if (codes && codes[0] && codes[0].rawValue) {
              handleDecoded(codes[0].rawValue);
            }
          } catch (_e) { /* */ }
        }, 400);
      } else {
        const mod = await import("html5-qrcode");
        const Html5Qrcode = mod.Html5Qrcode || mod.default?.Html5Qrcode;
        scannerRef.current = new Html5Qrcode("scan-region", false);
        scannerRef.current.start(
          { facingMode: "environment" }, { fps: 6, qrbox: 240 },
          (txt) => handleDecoded(txt), () => {},
        ).catch(() => {});
      }
    } catch (e) {
      setError(e?.name === "NotAllowedError"
        ? "Camera access denied. Enter token manually below."
        : "Couldn't start camera. Enter token manually below.");
    }
  };

  const submitManual = () => {
    const t = manualToken.trim();
    if (t.startsWith("stq_")) nav(`/scan-to-pay/${t}`);
    else setError("Token should start with 'stq_'.");
  };

  const bg = light ? "bg-white text-slate-900" : "bg-slate-950 text-white";

  return (
    <div className={`${bg} min-h-screen`} data-testid="scan-page">
      <div className="max-w-md mx-auto px-4 py-8">
        <button onClick={() => nav(-1)}
                        data-testid="scan-back"
                        className={`inline-flex items-center gap-1 text-xs
                                              ${light ? "text-slate-500" : "text-slate-400"}
                                              hover:opacity-80 mb-4`}>
          <ArrowLeft size={12} /> Back
        </button>
        <div className="flex items-center gap-3 mb-6">
          <div className="w-11 h-11 rounded-2xl grid place-items-center
                                      bg-gradient-to-br from-fuchsia-500 to-amber-500">
            <QrCode size={20} className="text-white" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
              Scan-to-Pay
            </div>
            <h1 className="text-2xl font-black">Scan a merchant QR</h1>
          </div>
        </div>

        {error && (
          <div className="rounded-xl px-4 py-3 bg-red-500/10 border
                                        border-red-500/40 text-red-400 text-sm
                                        inline-flex items-center gap-2 mb-4"
                    data-testid="scan-error">
            <AlertTriangle size={16} /> {error}
          </div>
        )}

        <div className={`aspect-square rounded-2xl border-2 overflow-hidden
                                        relative ${light ? "bg-slate-100 border-slate-200"
                                                                    : "bg-slate-900/60 border-slate-800"}`}>
          <video ref={videoRef}
                        data-testid="scan-video"
                        playsInline muted
                        className="w-full h-full object-cover"
                        style={{ display: scanning ? "block" : "none" }} />
          <div id="scan-region"
                    style={{ display: scanning ? "none" : "none" }} />
          {!scanning && (
            <div className="w-full h-full grid place-items-center
                                        text-center px-6">
              <div>
                <Camera size={56}
                                    className={light ? "text-slate-400" : "text-slate-500"} />
                <p className={`text-sm mt-3 ${light ? "text-slate-600" : "text-slate-400"}`}>
                  Point your camera at the merchant&rsquo;s QR to pay.
                </p>
                <button onClick={startScan}
                                data-testid="scan-start-btn"
                                className="mt-5 inline-flex items-center gap-2 font-black
                                                          text-sm px-5 py-2.5 rounded-full
                                                          bg-amber-500 text-slate-950 hover:bg-amber-400
                                                          shadow-lg shadow-amber-500/30">
                  <Camera size={16} /> Tap to Scan
                </button>
              </div>
            </div>
          )}
        </div>

        <div className={`mt-6 rounded-xl p-4 ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-900/60 border border-slate-800"}`}>
          <div className={`text-[10px] uppercase tracking-widest font-mono mb-2
                                        ${light ? "text-slate-500" : "text-slate-400"} inline-flex items-center gap-1`}>
            <Keyboard size={11} /> Or enter token manually
          </div>
          <div className="flex gap-2">
            <input value={manualToken}
                          onChange={(e) => setManualToken(e.target.value)}
                          data-testid="scan-manual-input"
                          placeholder="stq_..."
                          className={`flex-1 px-3 py-2 rounded-lg text-sm
                                                      ${light ? "bg-white border border-slate-300"
                                                                    : "bg-slate-900 border border-slate-700"}`} />
            <button onClick={submitManual}
                            data-testid="scan-manual-submit"
                            className="px-4 py-2 rounded-full bg-slate-800 text-white
                                                    text-xs font-black hover:bg-slate-700">
              Go
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
