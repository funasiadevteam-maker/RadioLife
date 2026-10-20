// Travel live search — Flights (Travelpayouts WL widget), Hotels (Klook) & Cars.
import { useState } from "react";
import { Plane, BedDouble, Car } from "lucide-react";
import TravelWidget from "./TravelWidget";
import TravelContentWidget from "./TravelContentWidget";

const KLOOK_HOTELS = "https://tpwidg.com/content?currency=USD&trs=587763&shmarker=174867&locale=en-US&city_id=2&category=4&amount=6&powered_by=true&campaign_id=137&promo_id=4497&sub_id=fuusic_app";
const CARS = "https://tpwidg.com/content?trs=587763&shmarker=174867&locale=en-US&country=153&city=68511&powered_by=true&campaign_id=87&promo_id=2466&sub_id=fuusic_app";

const TABS = [
  { k: "flights", Icon: Plane, label: "Flights" },
  { k: "hotels", Icon: BedDouble, label: "Hotels" },
  { k: "cars", Icon: Car, label: "Cars" },
];

export default function TravelLiveSearch() {
  const [tab, setTab] = useState("flights");
  return (
    <section className="fz-card rounded-2xl p-4" data-testid="travel-live-search">
      <div className="flex items-center gap-2 mb-3">
        <Plane size={18} className="fz-brand" />
        <h2 className="text-lg font-black fz-text">Search live deals</h2>
        <span className="ml-auto text-[10px] font-black text-white px-2 py-0.5 rounded-full"
          style={{ background: "var(--live)" }}>LIVE</span>
      </div>
      <div className="flex gap-2 mb-4">
        {TABS.map(({ k, Icon, label }) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`travel-tab-${k}`}
            className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-black transition ${tab === k ? "fz-grad" : "fz-card fz-text"}`}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>
      {tab === "flights" && <TravelWidget />}
      {tab === "hotels" && <TravelContentWidget key="hotels" src={KLOOK_HOTELS} />}
      {tab === "cars" && <TravelContentWidget key="cars" src={CARS} />}
    </section>
  );
}
