/** StationOfflineModal — Phase RELIABILITY.P2.
 *
 *  Renders when the imported-stream <audio> element fires an
 *  `error` event TWICE in quick succession for the same station.
 *  ImportedStreamBridge dispatches a `bigfm:station-offline`
 *  CustomEvent carrying the failing station id + display name; this
 *  component subscribes to that event, opens the modal, and gives
 *  the user two safe exits:
 *
 *    - "Try another station"  →  /live-radio  (browse feed already
 *                                  filters out dead rows server-side
 *                                  once /api/playback-errors flips
 *                                  the health status).
 *    - "Close"                →  dismiss modal, tear down the
 *                                  imported station via the store's
 *                                  clearImported() action.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { usePlayerStore } from "@/store/usePlayerStore";

export default function StationOfflineModal() {
  const [open, setOpen] = useState(false);
  const [station, setStation] = useState(null);
  const clearImported = usePlayerStore((s) => s.clearImported);
  const navigate = useNavigate();

  useEffect(() => {
    function onOffline(ev) {
      const detail = (ev && ev.detail) || {};
      setStation({
        id:   detail.station_id || null,
        name: detail.station_name || "This station",
      });
      setOpen(true);
    }
    window.addEventListener("bigfm:station-offline", onOffline);
    return () =>
      window.removeEventListener("bigfm:station-offline", onOffline);
  }, []);

  const handleClose = useCallback(() => {
    setOpen(false);
    try { clearImported(); } catch (_) { /* store race, ignore */ }
  }, [clearImported]);

  const handleTryAnother = useCallback(() => {
    setOpen(false);
    try { clearImported(); } catch (_) { /* store race, ignore */ }
    navigate("/live-radio");
  }, [clearImported, navigate]);

  return (
    <Dialog open={open} onOpenChange={(v) => {
      if (!v) handleClose();
    }}>
      <DialogContent
        data-testid="station-offline-modal"
        className="max-w-sm border-white/10 bg-neutral-950 text-neutral-100">
        <DialogHeader>
          <div className="mx-auto mb-2 flex h-12 w-12 items-center
                            justify-center rounded-full bg-amber-500/15">
            <AlertTriangle className="h-6 w-6 text-amber-400"
                            aria-hidden="true" />
          </div>
          <DialogTitle
            data-testid="station-offline-title"
            className="text-center text-lg font-semibold">
            Station is offline
          </DialogTitle>
          <DialogDescription
            data-testid="station-offline-body"
            className="text-center text-sm text-neutral-400">
            {station?.name ? `${station.name} isn’t broadcasting right now.`
                            : "This station isn’t broadcasting right now."}
            {" "}Pick another and we’ll keep it out of your feed until it’s back.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="mt-2 flex flex-col gap-2 sm:flex-col">
          <Button
            data-testid="station-offline-try-another"
            className="w-full bg-amber-500 text-neutral-950
                        hover:bg-amber-400"
            onClick={handleTryAnother}>
            Try another station
          </Button>
          <Button
            data-testid="station-offline-close"
            variant="ghost"
            className="w-full text-neutral-300 hover:text-neutral-100"
            onClick={handleClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
