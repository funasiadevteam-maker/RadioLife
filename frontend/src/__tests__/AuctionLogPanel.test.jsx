// Phase 18d.1 — AuctionLogPanel component-level tests.
//
// Two flows:
//   1. Table renders 20 rows in column order when 20 items returned.
//   2. Source-badge color/data attribute matches per source value.

import React from "react";
import {render, screen, waitFor} from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("axios", () => ({
  __esModule: true,
  default: {get: jest.fn(), defaults: {withCredentials: true}},
}));
const axios = require("axios").default;

const makeItems = (n) => Array.from({length: n}, (_, i) => ({
  auction_id:           `au_${i}`,
  timestamp:           new Date(Date.now() - i * 60000).toISOString(),
  source:                 (["direct", "sponsored", "private_marketplace",
                                    "gam", "openrtb", "house"])[i % 6],
  channel_id:         `ch_${i}`,
  advertiser_name: `Adv ${i}`,
  creative_title:     `Creative ${i}`,
  bid_price_cents:    100 + i,
  clear_price_cents: 50 + i,
  reason:                  i % 3 === 0 ? `Reason text ${i}` : undefined,
}));

describe("Phase 18d.1 — AuctionLogPanel", () => {
  beforeEach(() => { jest.clearAllMocks(); });

  test("renders 20 rows with the spec column order when 20 items return",
        async () => {
    axios.get.mockResolvedValue({data: {items: makeItems(20),
      total_in_window: 423, window_seconds: 86400}});
    const Panel = require("../components/AuctionLogPanel").default;
    render(<Panel />);
    await waitFor(() => expect(screen.getByTestId("auction-log-table"))
                                              .toBeInTheDocument());
    // Exactly 20 rows.
    const rows = Array.from({length: 20}, (_, i) =>
      screen.getByTestId(`auction-row-${i}`));
    expect(rows).toHaveLength(20);
    // Column order: Time | Source | Channel | Advertiser | Creative | Bid | Clear | Reason
    const headers = Array.from(
      screen.getByTestId("auction-log-table").querySelectorAll("th")
        ).map((th) => th.textContent.trim());
    expect(headers).toEqual(["Time", "Source", "Channel", "Advertiser",
                                                "Creative", "Bid", "Clear", "Reason"]);
    // Window-total surfaces in the header.
    expect(screen.getByTestId("auction-log-panel").textContent)
        .toMatch(/423.*in the past/i);
  });

  test("source-badge color/data attribute matches each source value",
        async () => {
    axios.get.mockResolvedValue({data: {items: makeItems(6),
      total_in_window: 6, window_seconds: 86400}});
    const Panel = require("../components/AuctionLogPanel").default;
    const {SOURCE_BADGE} = require("../components/AuctionLogPanel");
    render(<Panel />);
    await waitFor(() => expect(screen.getByTestId("auction-row-0"))
                                              .toBeInTheDocument());
    const sources = ["direct", "sponsored", "private_marketplace",
                                "gam", "openrtb", "house"];
    sources.forEach((src) => {
      const badge = screen.getByTestId(`source-badge-${src}`);
      expect(badge).toBeInTheDocument();
      expect(badge.getAttribute("data-source")).toBe(src);
      // Color band exposed on the badge — convert the inline rgb() back
      // to hex to compare against the SOURCE_BADGE table.
      const m = badge.style.color.match(/\d+/g);
      expect(m).not.toBeNull();
      const hex = "#" + m.slice(0, 3).map((n) =>
        Number(n).toString(16).padStart(2, "0")).join("");
      expect(hex.toLowerCase()).toBe(SOURCE_BADGE[src].color.toLowerCase());
    });
  });

  test("formatCents formats cents in eCPM-style + currency", () => {
    const {formatCents} = require("../components/AuctionLogPanel");
    expect(formatCents(245)).toBe("$2.45");
    expect(formatCents(100)).toBe("$1.00");
    expect(formatCents(0.5)).toBe("$0.0050");          // sub-cent → 4 decimals
    expect(formatCents(null)).toBe("—");
    expect(formatCents(undefined)).toBe("—");
  });
});
