// Travel live search — Flights (Travelpayouts WL widget) + Hotels (coming soon).
import { useState } from "react";
import { Plane, BedDouble } from "lucide-react";
import TravelWidget from "./TravelWidget";

export default function TravelLiveSearch() {
  const [tab, setTab] = useState("flights");
  const Tab = ({ k, Icon, label, soon }) => (
    <button onClick={() => setTab(k)} data-testid={`travel-tab-${k}`}
      className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-black transition ${tab === k ? "fz-grad" : "fz-card fz-text"}`}>
      <Icon size={15} /> {label}
      {soon && (
        <span className="text-[9px] font-black px-1.5 py-0.5 rounded-full"
          style={{ background: "var(--live)", color: "#fff" }}>SOON</span>
      )}
    </button>
  );
  return (
    <section className="fz-card rounded-2xl p-4" data-testid="travel-live-search">
      <div className="flex items-center gap-2 mb-3">
        <Plane size={18} className="fz-brand" />
        <h2 className="text-lg font-black fz-text">Search live deals</h2>
        <span className="ml-auto text-[10px] font-black text-white px-2 py-0.5 rounded-full"
          style={{ background: "var(--live)" }}>LIVE</span>
      </div>
      <div className="flex gap-2 mb-4">
        <Tab k="flights" Icon={Plane} label="Flights" />
        <Tab k="hotels" Icon={BedDouble} label="Hotels" soon />
      </div>
      {tab === "flights" ? (
        <TravelWidget />
      ) : (
        <div data-testid="travel-hotels-soon"
          className="flex flex-col items-center text-center gap-2 py-10 px-4">
          <div className="fz-brand-soft rounded-full p-4"><BedDouble size={28} className="fz-brand" /></div>
          <div className="text-lg font-black fz-text">Hotels are coming soon</div>
          <p className="text-sm fz-muted max-w-sm">
            We're adding Trip.com hotel search to FUUSIC Travel in the next few days.
            For now, use the Flights tab — you can add a hotel to any flight search with
            the "Show hotels" option.
          </p>
          <button onClick={() => setTab("flights")} data-testid="travel-hotels-to-flights"
            className="fz-grad rounded-full px-4 py-2 text-sm font-black mt-1">Search flights</button>
        </div>
      )}
    </section>
  );
}
