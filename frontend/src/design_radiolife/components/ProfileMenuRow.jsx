// Phase R.1 — ProfileMenuRow.  Icon · label · optional value · chevron.
import React from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

export default function ProfileMenuRow({ Icon, label, value, to, onClick,
                                                              danger = false,
                                                              testId }) {
  const inner = (
    <>
      <div className={"w-9 h-9 rounded-xl flex items-center justify-center " +
                              (danger ? "bg-pink-100 text-pink-600" : "bg-purple-100 text-purple-700")}>
        {Icon ? <Icon size={16} /> : null}
      </div>
      <div className="flex-1">
        <div className={"font-semibold " + (danger ? "text-pink-700" : "text-slate-900")}>
          {label}
        </div>
        {value && (
          <div className="text-[11px] uppercase tracking-wider text-slate-500 mt-0.5">
            {value}
          </div>
        )}
      </div>
      {!danger && <ChevronRight size={16} className="text-slate-400" />}
    </>
  );
  const cls = "w-full flex items-center gap-3 px-4 py-3 bg-white rounded-2xl " +
                    "border border-slate-100 hover:border-purple-200 " +
                    "hover:shadow-sm transition-all duration-150 text-left";
  if (to) {
    return (
      <Link to={to} data-testid={testId} className={cls}>{inner}</Link>
    );
  }
  return (
    <button type="button" onClick={onClick} data-testid={testId} className={cls}>
      {inner}
    </button>
  );
}
