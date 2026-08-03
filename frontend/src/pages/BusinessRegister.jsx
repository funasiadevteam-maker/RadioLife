// Phase I — Business Redemption Portal: register page.
// Requires the user to be authenticated (uses ProtectedRoute).  Captures
// storefront name, category, optional address + lat/lng, and a 4-digit
// POS-terminal PIN.  POST /api/business/register stores the hashed PIN
// and attaches the `business` role to the user.
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Loader2, Store, MapPin, Phone, Globe, KeyRound,
          ChevronRight } from "lucide-react";
import { Card, Button, Chip } from "@/shell/primitives";
import { API } from "@/AuthContext";

const CATEGORIES = ["cafe", "restaurant", "bar", "retail", "salon",
                                  "gym", "club", "venue", "service", "other"];

export default function BusinessRegister() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "", category: "cafe", address: "", phone: "", website: "",
    pin: "", pin2: "",
  });
  const [busy, setBusy] = useState(false);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    if (!/^\d{4}$/.test(form.pin)) {
      toast.error("PIN must be exactly 4 digits.");
      return;
    }
    if (form.pin !== form.pin2) {
      toast.error("PINs don't match.");
      return;
    }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/business/register`, {
        name: form.name.trim(),
        category: form.category,
        address: form.address.trim() || undefined,
        phone: form.phone.trim() || undefined,
        website: form.website.trim() || undefined,
        terminal_pin: form.pin,
      });
      if (r.data?.reason === "already_registered") {
        toast.message("You're already registered.");
      } else {
        toast.success("Welcome aboard! Your business is live.");
      }
      navigate("/business", { replace: true });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Registration failed.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="business-register-page"
            className="min-h-screen bg-bg-base px-4 py-12 flex justify-center">
      <Toaster richColors theme="dark" position="bottom-right" />
      <Card className="w-full max-w-xl p-8 space-y-6">
        <header className="space-y-2">
          <div className="inline-flex items-center gap-2 text-[10px]
                                  font-mono uppercase tracking-widest text-accent-gold">
            <Store size={11} /> BigFM Business Portal
          </div>
          <h1 className="font-display font-bold text-3xl tracking-display-tight">
            Register your <span className="text-accent-gold">storefront</span>
          </h1>
          <p className="text-text-secondary text-sm">
            One PIN at your counter is all you need to redeem coupons.
            BigFM never charges per redemption.
          </p>
        </header>

        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="text-xs text-text-secondary mb-1 block">Business name</span>
            <input type="text" value={form.name} required minLength={2} maxLength={120}
                          onChange={(e) => set("name", e.target.value)}
                          data-testid="business-register-name"
                          className="w-full rounded-token-md bg-white/[0.04] border border-white/10
                                          px-3.5 py-2.5 text-sm focus:outline-none focus:border-accent-gold/60" />
          </label>

          <div>
            <span className="text-xs text-text-secondary mb-1 block">Category</span>
            <div className="flex flex-wrap gap-1.5" data-testid="business-register-categories">
              {CATEGORIES.map((c) => (
                <button type="button" key={c} onClick={() => set("category", c)}
                                data-testid={`business-register-cat-${c}`}>
                  <Chip active={form.category === c}
                              tone={form.category === c ? "gold" : "neutral"}>
                    {c}
                  </Chip>
                </button>
              ))}
            </div>
          </div>

          <label className="block">
            <span className="text-xs text-text-secondary mb-1 block flex items-center gap-1.5">
              <MapPin size={11} /> Address (optional)
            </span>
            <input type="text" value={form.address}
                          onChange={(e) => set("address", e.target.value)}
                          data-testid="business-register-address"
                          className="w-full rounded-token-md bg-white/[0.04] border border-white/10
                                          px-3.5 py-2.5 text-sm focus:outline-none focus:border-accent-gold/60" />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs text-text-secondary mb-1 block flex items-center gap-1.5">
                <Phone size={11} /> Phone
              </span>
              <input type="tel" value={form.phone}
                            onChange={(e) => set("phone", e.target.value)}
                            data-testid="business-register-phone"
                            className="w-full rounded-token-md bg-white/[0.04] border border-white/10
                                            px-3.5 py-2.5 text-sm focus:outline-none focus:border-accent-gold/60" />
            </label>
            <label className="block">
              <span className="text-xs text-text-secondary mb-1 block flex items-center gap-1.5">
                <Globe size={11} /> Website
              </span>
              <input type="url" value={form.website}
                            onChange={(e) => set("website", e.target.value)}
                            data-testid="business-register-website"
                            className="w-full rounded-token-md bg-white/[0.04] border border-white/10
                                            px-3.5 py-2.5 text-sm focus:outline-none focus:border-accent-gold/60" />
            </label>
          </div>

          <div className="bg-accent-gold/[0.06] border border-accent-gold/20
                                  rounded-token-md p-4 space-y-3">
            <div className="flex items-center gap-2 text-accent-gold font-semibold text-sm">
              <KeyRound size={14} /> Terminal PIN
            </div>
            <p className="text-xs text-text-secondary">
              Pick a 4-digit code your staff will key in at redemption.
              You can change it later from the dashboard.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <input type="password" inputMode="numeric" maxLength={4} pattern="\d{4}"
                            value={form.pin} placeholder="1234" required
                            onChange={(e) => set("pin", e.target.value.replace(/\D/g, ""))}
                            data-testid="business-register-pin"
                            className="w-full rounded-token-md bg-white/[0.04] border border-white/10
                                            px-3.5 py-2.5 text-base tracking-[0.4em] text-center
                                            focus:outline-none focus:border-accent-gold/60" />
              <input type="password" inputMode="numeric" maxLength={4} pattern="\d{4}"
                            value={form.pin2} placeholder="Confirm" required
                            onChange={(e) => set("pin2", e.target.value.replace(/\D/g, ""))}
                            data-testid="business-register-pin2"
                            className="w-full rounded-token-md bg-white/[0.04] border border-white/10
                                            px-3.5 py-2.5 text-base tracking-[0.4em] text-center
                                            focus:outline-none focus:border-accent-gold/60" />
            </div>
          </div>

          <Button type="submit" variant="gold" className="w-full"
                          disabled={busy} data-testid="business-register-submit">
            {busy
              ? <><Loader2 size={14} className="animate-spin" /> Registering…</>
              : <>Open my portal <ChevronRight size={14} /></>}
          </Button>
        </form>
      </Card>
    </div>
  );
}
