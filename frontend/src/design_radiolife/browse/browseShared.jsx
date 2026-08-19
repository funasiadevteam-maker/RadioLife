// Shared helpers for the browse skins.
import React, { useState } from "react";

const BE = process.env.REACT_APP_BACKEND_URL || "";

export function mediaUrl(v) {
  if (!v) return null;
  if (/^https?:\/\//.test(v) || v.startsWith("data:")) return v;
  return `${BE}${v.startsWith("/") ? "" : "/"}${v}`;
}

const GRAD = [
  "from-orange-500 to-pink-600", "from-indigo-500 to-purple-600",
  "from-emerald-500 to-teal-600", "from-rose-500 to-red-600",
  "from-sky-500 to-blue-600", "from-amber-500 to-orange-600",
];

export function Art({ item, rounded = "rounded-lg" }) {
  const [err, setErr] = useState(false);
  const url = mediaUrl(item?.image);
  const g = GRAD[((item?.title || "?").charCodeAt(0) || 0) % GRAD.length];
  if (url && !err) {
    return (
      <img src={url} alt={item?.title || ""} loading="lazy" onError={() => setErr(true)}
        className={`object-cover w-full h-full ${rounded}`} />
    );
  }
  return (
    <div className={`w-full h-full ${rounded} bg-gradient-to-br ${g} flex items-center justify-center`}>
      <span className="text-white/90 font-black text-2xl">{(item?.title || "?").slice(0, 1)}</span>
    </div>
  );
}

export const NAV = [
  ["/", "Home"], ["/radio", "Radio"], ["/discover", "Discover"],
  ["/shop", "Shop"], ["/play", "Games"], ["/wallet", "Wallet"],
];
