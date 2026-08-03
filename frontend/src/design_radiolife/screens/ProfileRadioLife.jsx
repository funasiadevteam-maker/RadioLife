// Phase R.1 — Profile.
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import {
  CreditCard, Bell, Shield, HelpCircle, FileText, LogOut, User as UserIcon,
} from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import { RLCard, RLBadge, extractTier } from "../DesignSystem";
import ProfileMenuRow from "../components/ProfileMenuRow";

export default function ProfileRadioLife() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tier, setTier] = useState({ name: "Listener" });

  useEffect(() => {
    axios.get(`${API}/passport/me`, { withCredentials: true })
      .then((r) => setTier(extractTier(r.data)))
      .catch(() => {});
  }, []);

  const handleLogout = async () => {
    try {
      await logout?.();
    } catch { /* ignore */ }
    navigate("/login", { replace: true });
  };

  return (
    <div className="px-4 pt-6 pb-6 space-y-4" data-testid="rl-profile-page">
      {/* Avatar hero */}
      <RLCard gradient className="p-5 flex items-center gap-4">
        <div className="w-16 h-16 rounded-full bg-white/25 backdrop-blur
                                flex items-center justify-center flex-shrink-0">
          <UserIcon size={30} className="text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-black text-lg leading-tight truncate">
            {user?.display_name || user?.email?.split("@")[0] || "Friend"}
          </div>
          <div className="text-white/85 text-sm truncate">{user?.email}</div>
          <div className="mt-1.5">
            <RLBadge className="bg-white/25 text-white border border-white/25">
              {tier.name} Tier
            </RLBadge>
          </div>
        </div>
      </RLCard>

      {/* Menu */}
      <div className="space-y-2" data-testid="rl-profile-menu">
        <ProfileMenuRow Icon={CreditCard} label="Scan to pay"
                                    value="Tap to scan a merchant QR" to="/pay"
                                    testId="rl-profile-pay" />
        <ProfileMenuRow Icon={Bell} label="Notifications"
                                    to="/profile"
                                    testId="rl-profile-notifications" />
        <ProfileMenuRow Icon={Shield} label="Privacy & Security"
                                    to="/privacy"
                                    testId="rl-profile-privacy" />
        <ProfileMenuRow Icon={HelpCircle} label="Help & Support"
                                    to="/community"
                                    testId="rl-profile-help" />
        <ProfileMenuRow Icon={FileText} label="Terms & Privacy"
                                    to="/terms"
                                    testId="rl-profile-terms" />
        <ProfileMenuRow Icon={LogOut} label="Log Out" danger
                                    onClick={handleLogout}
                                    testId="rl-profile-logout" />
      </div>
      <div className="text-center text-[11px] uppercase tracking-widest text-slate-400
                              font-semibold pt-2">
        BigFM · RadioLife design
      </div>
    </div>
  );
}
