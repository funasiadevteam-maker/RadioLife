// Phase 18a — Settings (team + advertiser profile minimal).
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Users } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Settings({ advertiserId }) {
  const [adv, setAdv] = useState(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("manager");
  useEffect(() => {
    if (!advertiserId) return;
    axios.get(`${API}/advertiser/${advertiserId}`).then((r) => setAdv(r.data.advertiser)).catch(() => {});
  }, [advertiserId]);
  const invite = async () => {
    if (!email) return;
    try {
      await axios.post(`${API}/advertiser/${advertiserId}/staff`, { email, role });
      toast.success("teammate added");
      setEmail("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "add failed");
    }
  };
  if (!adv) return <div className="text-text-secondary">Loading...</div>;
  return (
    <div className="space-y-4" data-testid="advertiser-settings">
      <h2 className="font-display font-bold text-2xl">Settings</h2>
      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-5">
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">Profile</div>
        <div className="font-display font-bold text-lg mt-1">{adv.name}</div>
        <div className="text-xs text-text-secondary">{adv.contact_email} · {adv.market}</div>
      </div>
      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-5 space-y-2"
                  data-testid="settings-team-card">
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">
          <Users size={11} className="inline mr-1" /> Invite teammate
        </div>
        <div className="flex gap-2">
          <input type="email" className="bigfm-input flex-1" placeholder="teammate@example.com"
                    value={email} onChange={(e) => setEmail(e.target.value)} />
          <select className="bigfm-input" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="manager">manager</option>
            <option value="analyst">analyst</option>
          </select>
          <button className="bigfm-cta" onClick={invite}>Add</button>
        </div>
      </div>
    </div>
  );
}
