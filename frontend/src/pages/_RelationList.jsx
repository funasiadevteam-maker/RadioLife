// Phase MER.4 — Shared list UI for followed / saved businesses.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, ShieldCheck, ArrowLeft, MapPin, Sparkles } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

export function RelationList({ testid, endpoint, title, emptyLabel, icon }) {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user, loading: authLoading } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { setLoading(false); return; }
    (async () => {
      try {
        const { data } = await axios.get(endpoint, { withCredentials: true });
        setItems(data.items || []);
      } catch (e) {
        toast.error(`Load failed: ${e.message}`);
      } finally { setLoading(false); }
    })();
  }, [endpoint, user, authLoading]);

  const bgClass = light
    ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
    : "min-h-screen bg-slate-950 text-slate-100";

  if (authLoading || loading) return (
    <div className={`${bgClass} flex items-center justify-center`}
              data-testid={`${testid}-loading`}>
      <Loader2 className="animate-spin" size={30}/>
    </div>);

  if (!user) return (
    <div className={`${bgClass} flex items-center justify-center p-6`}
              data-testid={`${testid}-anon`}>
      <div className={`max-w-sm rounded-3xl p-6 text-center ${
        light ? "bg-white border border-slate-100 shadow-sm"
                : "bg-slate-900 border border-slate-800"}`}>
        <h1 className={`text-2xl font-black ${
          light ? "text-slate-900" : "text-white"}`}>Sign in first</h1>
        <Link to="/login" className="mt-4 inline-block h-10 rounded-full px-5 text-xs font-black text-white leading-[40px]"
                    style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>Sign in</Link>
      </div>
    </div>);

  return (
    <div className={`${bgClass} p-4 sm:p-8`} data-testid={`${testid}-page`}>
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-2 mb-4">
          <Link to="/" className={`text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
            <ArrowLeft className="inline" size={12}/> Home
          </Link>
        </div>
        <h1 className={`text-3xl font-black tracking-tight mb-6 ${
          light ? "text-slate-900" : "text-white"}`}>{title}</h1>

        {items.length === 0 ? (
          <div className={`rounded-3xl p-10 text-center ${
            light ? "bg-white border border-slate-100 shadow-sm"
                    : "bg-slate-900 border border-slate-800"}`}
                data-testid={`${testid}-empty`}>
            <div className="opacity-70 mb-2">{icon || <Sparkles size={30}/>}</div>
            <p className={`text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
              {emptyLabel}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3"
                data-testid={`${testid}-grid`}>
            {items.map(b => (
              <Link key={b.merchant_id} to={`/business/${b.slug || b.merchant_id}`}
                          data-testid={`${testid}-row-${b.merchant_id}`}
                          className={`flex items-center gap-3 rounded-3xl p-4 hover:scale-[1.01] transition-transform ${
                            light ? "bg-white border border-slate-100 shadow-sm"
                                    : "bg-slate-900 border border-slate-800"}`}>
                {b.logo_url ? (
                  <img src={b.logo_url.startsWith("http") ? b.logo_url : `${process.env.REACT_APP_BACKEND_URL}${b.logo_url}`}
                            alt="" className="w-14 h-14 rounded-2xl object-cover flex-shrink-0"/>
                ) : (
                  <div className={`w-14 h-14 rounded-2xl flex-shrink-0 ${
                    light ? "bg-gradient-to-br from-purple-100 to-pink-100"
                            : "bg-gradient-to-br from-cyan-500/20 to-purple-500/20"}`}/>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <h3 className={`text-base font-black truncate ${
                      light ? "text-slate-900" : "text-white"}`}>{b.name}</h3>
                    {b.verified && (
                      <ShieldCheck size={14} color={light ? "#059669" : "#34d399"}/>
                    )}
                  </div>
                  {b.category && (
                    <div className={`text-[10px] font-bold uppercase tracking-widest ${
                      light ? "text-purple-600" : "text-cyan-400"}`}>{b.category}</div>
                  )}
                  {b.city && (
                    <div className={`text-xs mt-0.5 ${
                      light ? "text-slate-500" : "text-slate-500"}`}>
                      <MapPin className="inline" size={10}/> {b.city}
                    </div>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
