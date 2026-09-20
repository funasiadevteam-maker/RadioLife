// Phase J.3 — Stripe checkout return pages.
// On `success`: poll /api/payments/{id}/status until status=paid (max 20s).
// On `cancel`: friendly toast + return to the entity's draft.
import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Card, Button } from "@/shell/primitives";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function CheckoutSuccess() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const sid = params.get("session_id") || params.get("checkout_session_id");
  const [status, setStatus] = useState("polling");
  const [doc, setDoc] = useState(null);

  useEffect(() => {
    if (!sid) { setStatus("error"); return; }
    let cancelled = false;
    let attempts = 0;
    const tick = async () => {
      if (cancelled) return;
      attempts += 1;
      try {
        const r = await axios.get(`${API}/payments/${sid}/status`);
        if (cancelled) return;
        setDoc(r.data);
        if (r.data?.status === "paid") {
          setStatus("paid");
          return;
        }
      } catch (_e) { /* ignored */ }
      if (attempts < 20) {
        setTimeout(tick, 1000);
      } else {
        setStatus("timeout");
      }
    };
    tick();
    return () => { cancelled = true; };
  }, [sid]);

  const goToEntity = () => {
    if (!doc) return navigate("/");
    if (doc.purpose === "predict_win_campaign") {
      navigate(`/advertiser/predict-win/${doc.entity_id}?paid=1`);
    } else if (doc.purpose === "business_ad_buy") {
      navigate("/business/campaigns");
    } else if (doc.purpose === "banner_ad_campaign") {
      navigate("/advertiser?paid=1");
    } else {
      navigate("/");
    }
  };

  return (
    <div data-testid="checkout-success-page"
            className="min-h-screen bg-bg-base flex items-center justify-center px-4">
      <Card className="max-w-md w-full p-6 sm:p-8 text-center space-y-4">
        {status === "polling" && (
          <>
            <Loader2 size={32} className="text-accent-electric mx-auto animate-spin" />
            <h1 className="font-display font-bold text-2xl tracking-display-tight">
              Confirming your payment…
            </h1>
            <p className="text-sm text-text-secondary">
              Stripe is finalising the charge. This usually takes 2-5 seconds.
            </p>
          </>
        )}
        {status === "paid" && (
          <>
            <CheckCircle2 size={36} className="text-accent-gold mx-auto" />
            <h1 className="font-display font-bold text-2xl tracking-display-tight">
              Payment complete
            </h1>
            <p className="text-sm text-text-secondary">
              ${(((doc?.amount_cents) || 0) / 100).toFixed(2)} {(doc?.currency || "USD").toUpperCase()}
              {" "}was charged. Your campaign is now in the approval queue.
            </p>
            <Button variant="gold" onClick={goToEntity}
                            data-testid="checkout-success-cta">
              Go to my campaign →
            </Button>
          </>
        )}
        {status === "timeout" && (
          <>
            <Loader2 size={32} className="text-accent-magenta mx-auto" />
            <h1 className="font-display font-bold text-2xl tracking-display-tight">
              Still confirming…
            </h1>
            <p className="text-sm text-text-secondary">
              The Stripe webhook is taking longer than expected. Your
              charge has gone through — refresh in a minute to see the
              campaign in the approval queue.
            </p>
            <Button variant="outline" onClick={goToEntity}
                            data-testid="checkout-success-cta">
              View my campaign anyway
            </Button>
          </>
        )}
        {status === "error" && (
          <>
            <XCircle size={32} className="text-rose-400 mx-auto" />
            <h1 className="font-display font-bold text-2xl tracking-display-tight">
              Couldn&apos;t find your session
            </h1>
            <Button variant="outline" onClick={() => navigate("/")}
                            data-testid="checkout-success-cta">
              Back to FUUSIC
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}


export function CheckoutCancel() {
  const navigate = useNavigate();
  useEffect(() => {
    toast.message("Payment cancelled — your draft was saved.");
  }, []);
  return (
    <div data-testid="checkout-cancel-page"
            className="min-h-screen bg-bg-base flex items-center justify-center px-4">
      <Card className="max-w-md w-full p-6 sm:p-8 text-center space-y-4">
        <XCircle size={36} className="text-text-secondary mx-auto" />
        <h1 className="font-display font-bold text-2xl tracking-display-tight">
          Payment cancelled
        </h1>
        <p className="text-sm text-text-secondary">
          No charges were made. Your campaign draft is saved — you can
          finish checkout any time.
        </p>
        <Button variant="outline" onClick={() => navigate(-1)}
                        data-testid="checkout-cancel-back">
          Back to draft
        </Button>
      </Card>
    </div>
  );
}
