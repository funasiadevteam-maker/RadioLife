// Phase K — M3 Wallet-Deal Marketplace · listener browse.
// URL: /marketplace  (chose /marketplace over /deals — /offers is
// already used by the AD.4-only CouponOffers page).
// Dual-design (Legacy dark + RadioLife light).  Grid of listings with
// featured-first placement, filter chips, save + view impressions.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  Loader2, Sparkles, Search, Bookmark, BookmarkCheck,
  Store, ChevronDown, ExternalLink,
} from "lucide-react";
import { toast } from "sonner";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { useGeoStore } from "@/store/useGeoStore";
import { useAuth } from "@/AuthContext";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const SORT_OPTIONS = [
  { value: "featured", label: "Featured" },
  { value: "newest",    label: "Newest" },
  { value: "value",      label: "Best value" },
];
const CATEGORIES = ["", "coupon", "merchant", "food", "retail", "beauty"];


export default function MarketplacePage() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const country = useGeoStore((s) => s.country);
  const { user } = useAuth();

  const region = (country || "").toLowerCase() || "ae";
  const [items, setItems] = useState(null);
  const [total, setTotal] = useState(0);
  const [featuredCount, setFeaturedCount] = useState(0);
  const [saved, setSaved] = useState({});    // {listing_id: {ok, wallet_item_id}}
  const [savingId, setSavingId] = useState(null);
  const [sort, setSort] = useState("featured");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const params = new URLSearchParams();
      params.set("region_code", region);
      params.set("sort_by", sort);
      if (category) params.set("category", category);
      if (search.trim()) params.set("search", search.trim());
      params.set("limit", "50");
      const { data } = await axios.get(`${API}/marketplace/listings?${params}`);
      setItems(data.items || []);
      setTotal(data.total || 0);
      setFeaturedCount(data.featured_count || 0);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [region, sort, category, search]);
  useEffect(() => { load(); }, [load]);

  const save = async (listing) => {
    if (!user) {
      toast.error("Please sign in to save deals.");
      return;
    }
    setSavingId(listing.listing_id);
    try {
      const { data } = await axios.post(
        `${API}/marketplace/listings/${listing.listing_id}/save`, {},
        { withCredentials: true });
      setSaved((s) => ({ ...s,
                                    [listing.listing_id]: {
                                      ok: true,
                                      wallet_item_id: data.wallet_item_id,
                                      already: !!data.already_saved,
                                    }}));
      toast.success(data.already_saved
        ? "Already in your wallet."
        : "Saved to wallet!");
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || e.message);
    } finally {
      setSavingId(null);
    }
  };

  // Best-effort impression on grid render.
  useEffect(() => {
    if (!items || items.length === 0 || !user) return;
    const featured = items.filter((it) => it.featured_slot_id).slice(0, 3);
    featured.forEach((it) => {
      axios.post(
        `${API}/marketplace/listings/${it.listing_id}/view`,
        { region_code: region },
        { withCredentials: true, timeout: 4000 })
          .catch(() => {});
    });
  }, [items, region, user]);

  const bg = light ? "bg-slate-50 text-slate-900" : "bg-slate-950 text-white";
  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div className={`min-h-screen ${bg} p-6`}
              data-testid="marketplace-page" data-variant={variant}>
      <div className="max-w-7xl xl:max-w-[1400px] mx-auto">
        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
          <h1 className="text-3xl md:text-4xl xl:text-5xl font-black inline-flex items-center gap-2">
            <Sparkles className="text-fuchsia-500" size={28} />
            Deal Marketplace
          </h1>
          <div className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}
                      data-testid="marketplace-region">
            Region: {region.toUpperCase()} · {total} deals
          </div>
        </div>
        <p className={`text-sm ${muted} mb-6`}>
          Coupons, vouchers and merchant offers you can save straight to your wallet.
          {featuredCount > 0
            ? " Featured deals are highlighted at the top."
            : ""}
        </p>

        {/* Filters */}
        <div className="flex flex-wrap gap-2 mb-4">
          <div className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5
                                                          ${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"}`}>
            <Search size={12} className={muted} />
            <input type="text" value={search}
                          onChange={(e) => setSearch(e.target.value)}
                          onKeyDown={(e) => { if (e.key === "Enter") load(); }}
                          placeholder="Search deals…"
                          data-testid="marketplace-search"
                          className={`bg-transparent text-xs outline-none w-32 sm:w-40 ${
                                                          light ? "text-slate-900" : "text-white"}`} />
          </div>
          <FilterChip value={category} onChange={setCategory} options={CATEGORIES}
                                    label="Category" light={light} testId="marketplace-cat-filter" />
          <FilterChip value={sort} onChange={setSort} options={SORT_OPTIONS.map((o) => o.value)}
                                    labels={SORT_OPTIONS} light={light}
                                    label="Sort" testId="marketplace-sort" />
        </div>

        {err && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                        text-red-400 text-xs px-3 py-2 mb-3"
                      data-testid="marketplace-error">{err}</div>
        )}
        {items === null ? (
          <div className={`inline-flex items-center gap-2 ${muted}`}
                      data-testid="marketplace-loading">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading deals…
          </div>
        ) : items.length === 0 ? (
          <div className={`rounded-2xl p-8 text-center text-sm ${
                                          light ? "bg-white border border-slate-200 text-slate-500"
                                                      : "bg-slate-900/60 border border-slate-800 text-slate-400"}`}
                      data-testid="marketplace-empty">
            No deals in {region.toUpperCase()} yet — check back soon.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3
                                          xl:grid-cols-4 2xl:grid-cols-5 gap-4"
                      data-testid="marketplace-grid">
            {items.map((it) => (
              <DealCard key={it.listing_id} listing={it} light={light}
                                        saving={savingId === it.listing_id}
                                        savedState={saved[it.listing_id]}
                                        onSave={() => save(it)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


function DealCard({ listing, light, saving, savedState, onSave }) {
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const isFeatured = !!listing.featured_slot_id;
  const isSaved = savedState?.ok;

  return (
    <div className={`${card} rounded-2xl overflow-hidden transition
                                          ${isFeatured ? "ring-2 ring-fuchsia-500/50" : ""}`}
              data-testid={`marketplace-card-${listing.listing_id}`}
              data-featured={isFeatured ? "1" : "0"}>
      {listing.image_url ? (
        <div className="aspect-video bg-slate-900 relative">
          <img src={listing.image_url} alt="" loading="lazy"
                    className="w-full h-full object-cover"
                    onError={(e) => (e.target.style.display = "none")} />
          {isFeatured && (
            <span className="absolute top-2 left-2 text-[10px] font-mono
                                              uppercase tracking-widest px-2 py-0.5 rounded-full
                                              bg-fuchsia-500 text-white"
                        data-testid={`marketplace-card-featured-${listing.listing_id}`}>
              Featured
            </span>
          )}
        </div>
      ) : (
        <div className={`aspect-video grid place-items-center ${
                                          light ? "bg-slate-100" : "bg-slate-950"}`}>
          <Store size={36} className={muted} />
          {isFeatured && (
            <span className="absolute top-2 left-2 text-[10px] font-mono
                                              uppercase tracking-widest px-2 py-0.5 rounded-full
                                              bg-fuchsia-500 text-white"
                        data-testid={`marketplace-card-featured-${listing.listing_id}`}>
              Featured
            </span>
          )}
        </div>
      )}
      <div className="p-4">
        <div className={`text-[10px] font-mono uppercase tracking-widest ${muted} mb-1`}>
          {listing.category} · {listing.source_type.replace("_", " ")}
        </div>
        <h3 className="text-base font-black mb-1 line-clamp-2">
          {listing.title}
        </h3>
        {listing.subtitle && (
          <p className={`text-xs ${muted} line-clamp-2 mb-2`}>
            {listing.subtitle}
          </p>
        )}
        <div className="flex items-baseline justify-between mt-3">
          <div className="text-lg font-black text-fuchsia-500"
                      data-testid={`marketplace-card-value-${listing.listing_id}`}>
            {listing.deal_value_cents > 0
              ? `$${(listing.deal_value_cents / 100).toFixed(2)}`
              : "Save it"}
          </div>
          <button onClick={onSave} disabled={saving || isSaved}
                          data-testid={`marketplace-card-save-${listing.listing_id}`}
                          className={`text-[11px] font-mono uppercase tracking-widest
                                                      px-3 py-1.5 rounded-full inline-flex items-center gap-1
                                                      ${isSaved
                                                          ? "bg-emerald-500/10 border border-emerald-500/40 text-emerald-500"
                                                          : "bg-fuchsia-500 text-white hover:bg-fuchsia-400"}
                                                      disabled:opacity-40`}>
            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> :
              isSaved ? <BookmarkCheck size={12} /> : <Bookmark size={12} />}
            {isSaved ? "Saved" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}


function FilterChip({ value, onChange, options, labels, label, light, testId }) {
  const muted = light ? "text-slate-500" : "text-slate-400";
  return (
    <div className={`relative inline-flex items-center gap-1 rounded-full px-3 py-1.5
                                    ${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"}`}>
      <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
        {label}:
      </span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
                      data-testid={testId}
                      className={`bg-transparent text-xs outline-none appearance-none pr-4 ${
                                                      light ? "text-slate-900" : "text-white"}`}>
        {options.map((o) => (
          <option key={o || "_all"} value={o}>
            {labels?.find((l) => l.value === o)?.label ||
              (o ? o.charAt(0).toUpperCase() + o.slice(1) : "All")}
          </option>
        ))}
      </select>
      <ChevronDown size={12} className={muted + " -ml-3 pointer-events-none"} />
    </div>
  );
}
