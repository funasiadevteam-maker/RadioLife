/**
 * Phase 39 Session 5/6 — PlacesAndRoutes UI Jest test.
 *
 * Tests:
 *  - 3 cards render
 *  - ✓ confirm + 🚫 hide POSTs fire
 *  - consent<3 empty state surfaces /privacy CTA
 */
import React from "react";
import "@testing-library/jest-dom";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PlacesAndRoutes from "../PlacesAndRoutes";
import axios from "axios";

jest.mock("axios");
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const renderPlaces = () =>
  render(<MemoryRouter><PlacesAndRoutes /></MemoryRouter>);


describe("PlacesAndRoutes", () => {
  beforeEach(() => { jest.clearAllMocks(); });

  test("renders 3 place cards when consent>=3", async () => {
    axios.get.mockImplementation((url) => {
      if (url.endsWith("/api/privacy/consent")) {
        return Promise.resolve({ data: { level: 3 } });
      }
      if (url.endsWith("/api/places/frequent")) {
        return Promise.resolve({
          data: {
            count: 3,
            places: [
              { place_id: "p1", label: "Home",       category: "home",
                visit_count: 40, last_seen: "2026-06-07T00:00:00Z" },
              { place_id: "p2", label: "Karak Cafe", category: "cafe",
                visit_count: 20, last_seen: "2026-06-06T00:00:00Z" },
              { place_id: "p3", label: "Gym",        category: "gym",
                visit_count: 12, last_seen: "2026-06-05T00:00:00Z" },
            ]
          }
        });
      }
      return Promise.resolve({ data: {} });
    });

    renderPlaces();

    await waitFor(() => {
      expect(screen.getByTestId("places-card-p1")).toBeInTheDocument();
      expect(screen.getByTestId("places-card-p2")).toBeInTheDocument();
      expect(screen.getByTestId("places-card-p3")).toBeInTheDocument();
    });
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Karak Cafe")).toBeInTheDocument();
  });


  test("confirm button POSTs and hide button POSTs", async () => {
    axios.get.mockImplementation((url) => {
      if (url.endsWith("/api/privacy/consent")) {
        return Promise.resolve({ data: { level: 3 } });
      }
      if (url.endsWith("/api/places/frequent")) {
        return Promise.resolve({
          data: {
            count: 1,
            places: [{ place_id: "p_only", label: "Coffee", category: "cafe",
                       visit_count: 7, last_seen: "2026-06-07T00:00:00Z" }]
          }
        });
      }
      return Promise.resolve({ data: {} });
    });
    axios.post.mockResolvedValue({ data: { ok: true } });

    renderPlaces();
    await waitFor(() => {
      expect(screen.getByTestId("places-confirm-p_only")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("places-confirm-p_only"));
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/places\/frequent\/p_only\/confirm$/),
        { confirmed: true },
        expect.any(Object)
      );
    });

    fireEvent.click(screen.getByTestId("places-hide-p_only"));
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/places\/frequent\/p_only\/hide$/),
        {},
        expect.any(Object)
      );
    });
  });


  test("consent<3 surfaces the /privacy CTA", async () => {
    axios.get.mockImplementation((url) => {
      if (url.endsWith("/api/privacy/consent")) {
        return Promise.resolve({ data: { level: 1 } });
      }
      return Promise.resolve({ data: {} });
    });

    renderPlaces();
    await waitFor(() => {
      expect(screen.getByTestId("places-empty-consent")).toBeInTheDocument();
      const cta = screen.getByTestId("places-enable-cta");
      expect(cta).toHaveAttribute("href", "/privacy");
    });
  });
});
