"""
Phase 15d — per-market lexicon used by AI prompt hardening.

The lexicon is the single source of truth for "what's local" in each market.
RJ scripts, trivia generation, ad copy and the AI Ad Creator all pull
`{local_brands_list}`, `{local_landmarks_list}`, `{local_food_examples}`
from here so we never leak Dubai vocabulary into a New York show.

Schema for each market:
    {
        "display_name":   str,     # human-friendly market label
        "country":         str,     # ISO-2 country code
        "timezone":        str,     # IANA tz string for daypart math
        "brands":          list[str],
        "landmarks":       list[str],
        "food":            list[str],
        "weather_idioms": list[str],
    }

When a request resolves a market that ISN'T in this dict we fall through to
`GENERIC_FALLBACK` so prompts still get scaffolding without inventing fake
local color.
"""
from __future__ import annotations
from typing import TypedDict, Dict, List


class MarketEntry(TypedDict, total=False):
    display_name:   str
    country:         str
    region:          str    # admin1 / state / county hint (optional)
    timezone:        str
    language:        str    # primary spoken language: 'hinglish' | 'english'
    centroid:        List[float]   # [lat, lng] — used by ipapi → market resolver
    brands:          List[str]
    landmarks:       List[str]
    food:            List[str]
    weather_idioms: List[str]


MARKET_LEXICON: Dict[str, MarketEntry] = {
    "dubai": {
        "display_name":   "Dubai",
        "country":         "AE",
        "timezone":        "Asia/Dubai",
        "language":        "hinglish",
        "centroid":        [25.2048, 55.2708],
        "brands":          ["Lulu", "Carrefour", "Talabat", "Careem", "Emirates",
                                    "Etisalat", "ADCB", "Costa Coffee"],
        "landmarks":       ["Burj Khalifa", "Dubai Marina", "JBR", "Palm Jumeirah",
                                    "Dubai Mall", "Sheikh Zayed Road", "Deira", "Bur Dubai"],
        "food":            ["karak chai", "shawarma", "manakish", "biryani",
                                    "machbous", "knafeh", "luqaimat", "mandi"],
        "weather_idioms": ["another scorcher", "stepping out of the AC",
                                    "humidity hitting", "sandstorm season"],
    },
    "new_york": {
        "display_name":   "New York",
        "country":         "US",
        "region":          "NY",
        "timezone":        "America/New_York",
        "language":        "english",
        "centroid":        [40.7128, -74.0060],
        "brands":          ["Duane Reade", "Trader Joe's", "Seamless", "MTA",
                                    "Citi Bike", "Chase", "Verizon", "Joe Coffee"],
        "landmarks":       ["Times Square", "Central Park", "Brooklyn Bridge",
                                    "Williamsburg", "the L train", "Grand Central",
                                    "Greenwich Village", "Hudson Yards"],
        "food":            ["bodega coffee", "dollar slice", "bagel and lox",
                                    "halal cart chicken & rice", "pastrami on rye",
                                    "egg-and-cheese on a roll", "black-and-white cookie",
                                    "deli sandwich"],
        "weather_idioms": ["that wind tunnel on 5th", "swamp summer",
                                    "subway-platform heat", "first snow on the stoop"],
    },
    "london": {
        "display_name":   "London",
        "country":         "GB",
        "timezone":        "Europe/London",
        "language":        "english",
        "centroid":        [51.5074, -0.1278],
        "brands":          ["Tesco", "Pret", "Deliveroo", "TfL", "Boots",
                                    "Sainsbury's", "Greggs", "Costa"],
        "landmarks":       ["the Thames", "Camden", "Shoreditch", "Soho",
                                    "the Tube", "Hyde Park", "South Bank", "Brick Lane"],
        "food":            ["proper roast", "chicken tikka masala", "a flat white",
                                    "salt-beef bagel", "Sunday roast", "fish and chips",
                                    "Brick Lane curry", "jacket potato"],
        "weather_idioms": ["four seasons in a day", "drizzle that's not rain",
                                    "tube-carriage steam", "blue-sky surprise"],
    },
    "mumbai": {
        "display_name":   "Mumbai",
        "country":         "IN",
        "timezone":        "Asia/Kolkata",
        "language":        "hinglish",
        "centroid":        [19.0760, 72.8777],
        "brands":          ["Big Bazaar", "Zomato", "Ola", "Vodafone Idea",
                                    "Reliance", "HDFC", "Starbucks Mumbai", "Theobroma"],
        "landmarks":       ["Marine Drive", "Bandra", "Andheri", "Juhu Beach",
                                    "Gateway of India", "the local", "Linking Road",
                                    "Powai"],
        "food":            ["cutting chai", "vada pav", "pav bhaji", "bhel puri",
                                    "Mumbai-style misal", "frankie", "kheema pav",
                                    "Irani chai"],
        "weather_idioms": ["monsoon arriving", "first rain off the sea",
                                    "humidity on the local", "muggy late evening"],
    },
    "los_angeles": {
        "display_name":   "Los Angeles",
        "country":         "US",
        "region":          "CA",
        "timezone":        "America/Los_Angeles",
        "language":        "english",
        "centroid":        [34.0522, -118.2437],
        "brands":          ["Trader Joe's", "Erewhon", "Postmates", "Metro",
                                    "Lyft", "Verizon", "In-N-Out", "Blue Bottle"],
        "landmarks":       ["the 405", "Sunset Strip", "Venice Beach", "Silver Lake",
                                    "DTLA", "Griffith Observatory", "Echo Park",
                                    "the Valley"],
        "food":            ["breakfast burrito", "In-N-Out animal-style",
                                    "Korean BBQ", "fish taco", "açai bowl",
                                    "kogi truck", "matcha latte", "pastrami sandwich"],
        "weather_idioms": ["June gloom", "Santa Ana winds", "marine layer morning",
                                    "endless blue sky"],
    },
    # Phase 15d.1 — Dallas–Fort Worth (DFW). The existing `user.market === "dfw"`
    # carve-out in Radio.js routes to FunAsia branding for legacy DFW users; the
    # geo-resolved DFW market defaults to the FUUSIC brand. The frontend reads
    # `users.funasia_brand_opt_in` (added in this phase) to decide which logo
    # to render — see Radio.js header logic.
    "dfw": {
        "display_name":   "Dallas",
        "country":         "US",
        "region":          "TX",
        "timezone":        "America/Chicago",
        "language":        "english",
        "centroid":        [32.7767, -96.7970],
        "brands":          ["H-E-B", "Whataburger", "Tom Thumb", "Buc-ee's",
                                    "Torchy's Tacos", "Velvet Taco", "Ascension Coffee",
                                    "AT&T"],
        "landmarks":       ["Reunion Tower", "AT&T Stadium", "Klyde Warren Park",
                                    "Deep Ellum", "Bishop Arts", "NorthPark Center",
                                    "White Rock Lake", "Trinity Groves", "Lower Greenville"],
        "food":            ["breakfast tacos", "Tex-Mex queso", "brisket plate",
                                    "kolaches", "Whataburger patty melt", "smoked ribs",
                                    "chicken-fried steak", "pecan pie"],
        "weather_idioms": ["Texas heat hitting", "cold front rolling in",
                                    "thunderstorm on the radar", "perfect patio weather",
                                    "humidity off the lake"],
    },
}


GENERIC_FALLBACK: MarketEntry = {
    "display_name":   "your city",
    "country":         "??",
    "timezone":        "UTC",
    "brands":          ["the corner store", "the local café", "the supermarket"],
    "landmarks":       ["downtown", "the river", "the main square",
                              "the train station"],
    "food":            ["a strong cup of coffee", "a hot breakfast",
                              "the local late-night spot"],
    "weather_idioms": ["the weather today", "this kind of evening"],
}


def get_lexicon(market: str | None) -> MarketEntry:
    """Return the lexicon entry for `market`, or GENERIC_FALLBACK if unknown.
    Market keys are normalised to lower-case-snake (e.g. 'New York' → 'new_york').
    """
    if not market:
        return GENERIC_FALLBACK
    key = market.strip().lower().replace(" ", "_").replace("-", "_")
    return MARKET_LEXICON.get(key, GENERIC_FALLBACK)


def supported_markets() -> List[str]:
    """All explicitly-supported market keys (for change-location dropdowns)."""
    return list(MARKET_LEXICON.keys())
