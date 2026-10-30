// Travel live search — Flights (WL widget), Hotels (Klook + city picker) & Cars.
import { useState } from "react";
import axios from "axios";
import { Plane, BedDouble, Car, Bookmark, Check } from "lucide-react";
import { API } from "@/AuthContext";
import TravelWidget from "./TravelWidget";
import TravelContentWidget from "./TravelContentWidget";

// Klook destination IDs drive the hotel widget's city_id.
const KLOOK_CITIES = [
  { id: 254, label: "Dubai", emoji: "🇦🇪" },
  { id: 3, label: "Singapore", emoji: "🇸🇬" },
  { id: 4, label: "Bangkok", emoji: "🇹🇭" },
  { id: 2, label: "Hong Kong", emoji: "🇭🇰" },
  { id: 25, label: "Tokyo", emoji: "🇯🇵" },
  { id: 50, label: "Seoul", emoji: "🇰🇷" },
  { id: 64, label: "Bali", emoji: "🇮🇩" },
  { id: 5, label: "Kuala Lumpur", emoji: "🇲🇾" },
  { id: 360, label: "London", emoji: "🇬🇧" },
  { id: 487, label: "Paris", emoji: "🇫🇷" },
];
const klookHotelsSrc = (cityId) =>
  `https://tpwidg.com/content?currency=USD&trs=587763&shmarker=174867&locale=en-US&city_id=${cityId}&category=4&amount=6&powered_by=true&campaign_id=137&promo_id=4497&sub_id=fuusic_app`;
const CARS = "https://tpwidg.com/content?trs=587763&shmarker=174867&locale=en-US&country=153&city=68511&powered_by=true&campaign_id=87&promo_id=2466&sub_id=fuusic_app";

const TABS = [
  { k: "flights", Icon: Plane, label: "Flights" },
  { k: "hotels", Icon: BedDouble, label: "Hotels" },
  { k: "cars", Icon: Car, label: "Cars" },
];

function SaveSearchBtn({ tripType, title, subtitle }) {
  const [done, setDone] = useState(false);
  const save = async () => {
    setDone(true);
    await axios.post(`${API}/travel/saved`, { trip_type: tripType, title, subtitle }).catch(() => {});
  };
  return (
    <button onClick={save} disabled={done} data-testid={`travel-save-${tripType}`}
      className="mt-3 w-full flex items-center justify-center gap-2 rounded-full py-2.5 text-sm font-black fz-card fz-text disabled:opacity-60">
      {done ? <><Check size={15} className="fz-brand" /> Saved to My Trips</>
            : <><Bookmark size={15} /> Save this search to My Trips</>}
    </button>
  );
}

export default function TravelLiveSearch() {
  const [tab, setTab] = useState("flights");
  const [hotelCity, setHotelCity] = useState(254);
  const cityLabel = (KLOOK_CITIES.find((c) => c.id === hotelCity) || {}).label || "Dubai";

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

      {tab === "hotels" && (
        <div>
          <div className="flex gap-2 overflow-x-auto pb-2 no-scrollbar mb-2" data-testid="hotels-city-picker">
            {KLOOK_CITIES.map((c) => (
              <button key={c.id} onClick={() => setHotelCity(c.id)} data-testid={`hotel-city-${c.id}`}
                className={`shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-bold ${hotelCity === c.id ? "fz-chip-active" : "fz-chip"}`}>
                {c.emoji} {c.label}
              </button>
            ))}
          </div>
          <TravelContentWidget key={`hotels-${hotelCity}`} src={klookHotelsSrc(hotelCity)} />
          <SaveSearchBtn tripType="hotel" title={`Hotels in ${cityLabel}`} subtitle="Saved hotel search" />
        </div>
      )}

      {tab === "cars" && (
        <div>
          <TravelContentWidget key="cars" src={CARS} />
          <SaveSearchBtn tripType="car" title="Car rental" subtitle="Saved car search" />
        </div>
      )}
    </section>
  );
}
