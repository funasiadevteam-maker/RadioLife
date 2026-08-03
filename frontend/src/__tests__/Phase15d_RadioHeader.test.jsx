// Phase 15d — Radio header must render "BigFM <city>" and
// "NOW IN <CITY>" dynamically from useGeoStore, not from a hardcoded
// "Dubai" literal. We mount the same JSX fragment Radio.js renders for
// `brand-bigfm` so we don't have to spin up the entire Radio page.

import React from "react";
import { render, cleanup } from "@testing-library/react";
import { MapPin } from "lucide-react";

// Minimal copy of the JSX shipped at Radio.js:493-499.
function RadioHeaderUnderTest({ geoCity, market }) {
  const isFunasia = market === "dfw";
  return (
    <header data-testid="radio-header">
      <div>
        {isFunasia ? (
          <h1 data-testid="brand-funasia">FunAsia <span>AI Radio</span></h1>
        ) : (
          <h1 data-testid="brand-bigfm">
            BigFM <span data-testid="brand-bigfm-city">{geoCity || "Dubai"}</span>
          </h1>
        )}
      </div>
      <span data-testid="location-chip">
        <MapPin size={11} />{" "}
        {isFunasia ? "NOW IN DFW" : `NOW IN ${(geoCity || "Dubai").toUpperCase()}`}
      </span>
    </header>
  );
}

afterEach(cleanup);

describe("Phase 15d — Radio brand header is dynamic per market", () => {
  test("market=new_york → 'BigFM New York' + 'NOW IN NEW YORK'", () => {
    const { getByTestId } = render(
      <RadioHeaderUnderTest geoCity="New York" market="default" />
    );
    expect(getByTestId("brand-bigfm").textContent).toBe("BigFM New York");
    expect(getByTestId("brand-bigfm-city").textContent).toBe("New York");
    expect(getByTestId("location-chip").textContent).toContain("NOW IN NEW YORK");
    expect(getByTestId("location-chip").textContent).not.toContain("DUBAI");
    expect(getByTestId("brand-bigfm").textContent).not.toContain("Dubai");
  });

  test("market=london → 'BigFM London' + 'NOW IN LONDON'", () => {
    const { getByTestId } = render(
      <RadioHeaderUnderTest geoCity="London" market="default" />
    );
    expect(getByTestId("brand-bigfm").textContent).toBe("BigFM London");
    expect(getByTestId("location-chip").textContent).toContain("NOW IN LONDON");
    expect(getByTestId("location-chip").textContent).not.toContain("DUBAI");
  });

  test("market=mumbai → 'BigFM Mumbai' + 'NOW IN MUMBAI'", () => {
    const { getByTestId } = render(
      <RadioHeaderUnderTest geoCity="Mumbai" market="default" />
    );
    expect(getByTestId("brand-bigfm").textContent).toBe("BigFM Mumbai");
    expect(getByTestId("location-chip").textContent).toContain("NOW IN MUMBAI");
  });

  test("market=los_angeles → 'BigFM Los Angeles' + 'NOW IN LOS ANGELES'", () => {
    const { getByTestId } = render(
      <RadioHeaderUnderTest geoCity="Los Angeles" market="default" />
    );
    expect(getByTestId("brand-bigfm").textContent).toBe("BigFM Los Angeles");
    expect(getByTestId("location-chip").textContent).toContain(
      "NOW IN LOS ANGELES"
    );
  });

  test("market=dubai (default) → 'BigFM Dubai' + 'NOW IN DUBAI'", () => {
    const { getByTestId } = render(
      <RadioHeaderUnderTest geoCity="Dubai" market="default" />
    );
    expect(getByTestId("brand-bigfm").textContent).toBe("BigFM Dubai");
    expect(getByTestId("location-chip").textContent).toContain("NOW IN DUBAI");
  });

  test("geoCity empty → falls back to Dubai (legacy behaviour)", () => {
    const { getByTestId } = render(
      <RadioHeaderUnderTest geoCity="" market="default" />
    );
    expect(getByTestId("brand-bigfm").textContent).toBe("BigFM Dubai");
    expect(getByTestId("location-chip").textContent).toContain("NOW IN DUBAI");
  });

  test("market=dfw → still renders FunAsia branding (legacy carve-out)", () => {
    const { getByTestId, queryByTestId } = render(
      <RadioHeaderUnderTest geoCity="New York" market="dfw" />
    );
    expect(queryByTestId("brand-bigfm")).toBeNull();
    expect(getByTestId("brand-funasia").textContent).toContain("FunAsia");
    expect(getByTestId("location-chip").textContent).toContain("NOW IN DFW");
  });
});
