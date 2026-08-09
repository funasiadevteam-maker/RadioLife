// Phase R.1 — Station row on Listen screen.
import React from "react";
import { Link } from "react-router-dom";
import { Play, Radio } from "lucide-react";
import { cn } from "@/lib/utils";

const API = process.env.REACT_APP_BACKEND_URL || "";

export default function StationRow({ channel }) {
  const artUrl = channel.thumbnail_url ? `${API}${channel.thumbnail_url}` : null;
  return (
    <Link
      to={`/radio/station/${channel.slug}`}
      data-testid={`rl-station-row-${channel.slug}`}
      className="flex items-center gap-3 p-3 bg-white rounded-2xl border
                          border-slate-100 hover:border-orange-200
                          hover:shadow-md hover:shadow-orange-500/5
                          transition-all duration-150">
      <div className="w-14 h-14 rounded-xl overflow-hidden flex-shrink-0
                              relative bg-orange-100 flex items-center justify-center">
        {artUrl ? (
          <img
            src={artUrl}
            alt={channel.name}
            className="absolute inset-0 w-full h-full object-cover"
            loading="lazy"
            onError={(e) => { e.currentTarget.style.display = "none"; }}
          />
        ) : (
          <Radio size={22} className="text-orange-500" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-bold text-slate-900 truncate">
          {channel.name || channel.slug}
        </div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold
                                mt-0.5 flex items-center gap-1.5">
          {channel.tagline && <span className="truncate">{channel.tagline}</span>}
          {channel.live && (
            <span className="inline-flex items-center gap-1 text-amber-600">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              LIVE
            </span>
          )}
        </div>
      </div>
      <div className={cn("w-10 h-10 rounded-full flex items-center justify-center",
                                    "text-white shadow-md")}
                style={{ background: "linear-gradient(135deg, #A020F0, #EC4899)" }}>
        <Play size={16} strokeWidth={2.5} fill="currentColor" />
      </div>
    </Link>
  );
}
