// Phase 18b polish — geo-label single-source-of-truth (FE).
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";

// Router shim.
jest.mock("react-router-dom", () => ({
  __esModule: true,
  useNavigate:     () => jest.fn(),
  useParams:       () => ({}),
  useSearchParams: () => [{ get: () => null }, jest.fn()],
  NavLink:          ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Link:             ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });

// Zustand store shim — return a deterministic Dubai market.
jest.mock("@/store/useGeoStore", () => {
  const state = {
    market: "dubai", city: "Dubai",
    timezone: "Asia/Dubai", source: "user_profile",
    ready: true, loading: false,
  };
  const useGeoStore = (sel) => sel(state);
  useGeoStore.getState = () => state;
  return { __esModule: true, useGeoStore };
}, { virtual: true });

// Mock axios for LocalNewsWidget's GET /api/news/local call.
jest.mock("axios", () => {
  const get = jest.fn(async () => ({
    data: { items: [{ title: "Dubai Metro adds new line",
                              source_name: "Khaleej Times",
                              published_at: new Date().toISOString(),
                              url: "https://example.com/x" }] } }));
  return { __esModule: true, default: { get, defaults: { withCredentials: true } },
              get, defaults: { withCredentials: true } };
});


test("LocalNewsWidget header uses the same city as the geo store (Dubai) — no Dallas leak", async () => {
  const LocalNewsWidget = require("../components/LocalNewsWidget").default;
  render(<LocalNewsWidget />);
  // The widget header is "Around <city>" — must read "Around Dubai", never Dallas.
  await waitFor(() => {
    const txt = document.body.textContent || "";
    expect(txt).toMatch(/Around\s+Dubai/i);
    expect(txt).not.toMatch(/Around\s+Dallas/i);
  });
});
