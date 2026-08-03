/** Phase 42-E2.2 — Invite a friend form.
 *  Posts to /api/invite/send and surfaces the resulting referral code.
 *  Designed to drop straight into a Wallet / Passport / Home sidebar.
 */
import React, { useState } from "react";
import axios from "axios";
import { Mail, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/AuthContext";

export default function InviteFriendForm({ compact = false }) {
  const [email, setEmail] = useState("");
  const [name,  setName]  = useState("");
  const [note,  setNote]  = useState("");
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState(null);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || busy) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/invite/send`, {
        to_email:        email.trim(),
        to_name:        name.trim() || null,
        personal_note: note.trim() || null,
      }, { withCredentials: true });
      setLast({ code: r.data.code, status: r.data.email_status });
      toast.success(
        r.data.email_status === "sent_via_mailgun"
          ? `Invite emailed — code ${r.data.code}`
          : `Invite logged (email mocked) — code ${r.data.code}`);
      setEmail(""); setName(""); setNote("");
    } catch (err) {
      toast.error(err.response?.data?.detail?.message || "Couldn't send invite");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form data-testid="invite-friend-form"
                onSubmit={onSubmit}
                className={`rounded-2xl border border-white/[0.08]
                                    bg-white/[0.02] p-4 ${compact ? "" : "lg:p-5"}`}>
      <div className="flex items-center gap-2 mb-3">
        <Mail size={16} className="text-accent-electric" />
        <h3 className="font-display font-bold text-base tracking-display-tight">
          Invite a friend
        </h3>
      </div>
      <div className="space-y-2">
        <input
          type="email"
          required
          placeholder="friend@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          data-testid="invite-friend-email"
          className="w-full px-3 py-2 bg-black/30 border border-white/[0.1]
                                  rounded-lg text-sm text-white placeholder-white/30
                                  focus:outline-none focus:border-accent-electric/60"
        />
        {!compact && (
          <input
            type="text"
            placeholder="Their name (optional)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          data-testid="invite-friend-name"
            className="w-full px-3 py-2 bg-black/30 border border-white/[0.1]
                                    rounded-lg text-sm text-white placeholder-white/30
                                    focus:outline-none focus:border-accent-electric/60"
          />
        )}
        {!compact && (
          <textarea
            placeholder="Add a personal note (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            maxLength={500}
            data-testid="invite-friend-note"
            className="w-full px-3 py-2 bg-black/30 border border-white/[0.1]
                                    rounded-lg text-sm text-white placeholder-white/30
                                    focus:outline-none focus:border-accent-electric/60"
          />
        )}
        <button
          type="submit"
          disabled={busy || !email.trim()}
          data-testid="invite-friend-submit"
          className="w-full mt-1 inline-flex items-center justify-center gap-2
                                  px-3 py-2 rounded-lg bg-accent-electric/90 text-black
                                  font-display font-bold text-sm
                                  disabled:opacity-40 disabled:cursor-not-allowed
                                  hover:bg-accent-electric transition-colors">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Mail size={14} />}
          {busy ? "Sending…" : "Send invite — earn 5 points"}
        </button>
      </div>
      {last && (
        <div data-testid="invite-result"
                  data-code={last.code}
                  data-status={last.status}
                  className="mt-3 text-xs text-white/60 leading-relaxed">
          Their referral code: <code className="text-accent-electric">{last.code}</code>
          {last.status !== "sent_via_mailgun" && (
            <span className="ml-1 text-amber-300/80">(email mocked)</span>
          )}
        </div>
      )}
    </form>
  );
}
