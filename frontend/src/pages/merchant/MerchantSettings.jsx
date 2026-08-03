// Phase MER.1 — Merchant Settings (minimal — logo, hours, sign-out).
import { useState } from "react";
import { Link } from "react-router-dom";
import { Store, LogOut, ChevronRight, Shield } from "lucide-react";
import { useMerchant } from "@/pages/merchant/MerchantShell";
import { useAuth } from "@/AuthContext";


export default function MerchantSettings() {
  const { merchant, light } = useMerchant();
  const { logout, user } = useAuth();

  return (
    <div className="p-6 lg:p-10 max-w-3xl mx-auto space-y-5"
              data-testid="merchant-settings-page">
      <h1 className={`text-3xl font-black tracking-tight ${
        light ? "text-slate-900" : "text-white"
      }`}>Settings</h1>

      {/* Account row */}
      <SettingsCard light={light} testid="merchant-settings-account">
        <SettingsRow light={light} label="Owner email"
                                  value={user?.email || "—"}
                                  Icon={Shield}/>
        <SettingsRow light={light} label="Category"
                                  value={(merchant.category_id || "—").replace(/_/g, " ")}
                                  Icon={Store}/>
        <SettingsRow light={light} label="Merchant ID"
                                  value={<code className="text-xs">{merchant.merchant_id}</code>}
                                  Icon={Shield}/>
      </SettingsCard>

      {/* Links to related pages */}
      <SettingsCard light={light} testid="merchant-settings-shortcuts">
        <SettingsLink light={light} to="/merchant/profile"
                                    label="Edit profile & locations"
                                    testid="merchant-settings-goto-profile"/>
        <SettingsLink light={light} to="/merchant/stripe"
                                    label="Stripe Connect status"
                                    testid="merchant-settings-goto-stripe"/>
        <SettingsLink light={light} to="/merchant/payouts"
                                    label="Payouts history"
                                    testid="merchant-settings-goto-payouts"/>
      </SettingsCard>

      {/* Sign out */}
      <SettingsCard light={light}>
        <button onClick={logout}
                      data-testid="merchant-settings-signout"
                      className={`w-full flex items-center gap-3 p-4 text-left ${
                        light ? "text-rose-700 hover:bg-rose-50"
                                : "text-rose-300 hover:bg-rose-500/10"
                      }`}>
          <LogOut size={16}/>
          <span className="font-semibold text-sm">Sign out</span>
        </button>
      </SettingsCard>

      <div className={`text-center text-[10px] font-black uppercase tracking-widest ${
        light ? "text-slate-500" : "text-slate-500"
      }`}>
        BigFM Merchant Portal · Track 2
      </div>
    </div>
  );
}


function SettingsCard({ light, testid, children }) {
  return (
    <div className={`rounded-2xl overflow-hidden ${
      light ? "bg-white border border-slate-100 shadow-sm"
              : "bg-slate-900 border border-slate-800"
    }`} data-testid={testid}>
      {children}
    </div>
  );
}


function SettingsRow({ light, label, value, Icon }) {
  return (
    <div className={`flex items-center gap-3 p-4 border-t first:border-t-0 ${
      light ? "border-slate-100" : "border-slate-800"
    }`}>
      <Icon size={16} className={light ? "text-slate-500" : "text-slate-500"}/>
      <div className={`text-xs uppercase tracking-widest font-bold ${
        light ? "text-slate-500" : "text-slate-500"
      }`}>{label}</div>
      <div className={`ml-auto text-sm font-semibold ${
        light ? "text-slate-800" : "text-slate-200"
      }`}>{value}</div>
    </div>
  );
}


function SettingsLink({ light, to, label, testid }) {
  return (
    <Link to={to} data-testid={testid}
                className={`flex items-center gap-3 p-4 border-t first:border-t-0 ${
                  light ? "border-slate-100 hover:bg-slate-50 text-slate-800"
                          : "border-slate-800 hover:bg-slate-950 text-slate-200"
                }`}>
      <span className="font-semibold text-sm flex-1">{label}</span>
      <ChevronRight size={16} className={light ? "text-slate-400" : "text-slate-500"}/>
    </Link>
  );
}
