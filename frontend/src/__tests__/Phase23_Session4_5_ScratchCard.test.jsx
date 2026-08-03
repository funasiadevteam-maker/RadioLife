// Phase 23 Session 4.5d — ScratchCardGame (CSS-mask rewrite) tests.
//   - Component renders sponsor pill, prize layer, NEW foil layer
//   - Foil layer carries the silver/charcoal gradient backgroundImage
//   - Brand color flows into the `--brand` CSS variable
//   - Pointer-down + dragging samples enough dots to cross 60% coverage
//     and fires onSubmit() exactly once with scratched_pct >= 0.6
//   - After threshold, foil layer carries the "revealed" class + opacity 0
//   - Hint pill disappears after the first scratch
//
// NOTE: jsdom does NOT lay out DOM elements, so
// `getBoundingClientRect()` returns all-zeros.  The component bypasses
// this by setting `stageRectRef` to a fixed {0,0,STAGE_W,STAGE_H} on
// the legacy `onMouseDown` path used by jest/jsdom tests.
import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import "@testing-library/jest-dom";

import ScratchCardGame from "@/components/games/ScratchCardGame";


describe("Phase 23 Session 4.5d — ScratchCardGame (CSS-mask)", () => {
  test("renders sponsor pill + prize layer + foil layer with brand", () => {
    render(<ScratchCardGame
                config={{ type: "scratch_card",
                                  sponsor_name: "KARAK CAFE",
                                  prize_preview: { title: "Free Tiramisu",
                                                                value: "AED 24" } }}
                onSubmit={() => {}} submitting={false}
                result={null} brand="#ff2d95" />);
    expect(screen.getByTestId("scratch-card-game")).toBeInTheDocument();
    expect(screen.getByTestId("scratch-foil-layer")).toBeInTheDocument();
    expect(screen.getByTestId("scratch-prize-layer")).toBeInTheDocument();
    expect(screen.getByTestId("scratch-prize-title").textContent)
        .toMatch(/Free Tiramisu/);
    expect(screen.getByTestId("scratch-sponsor-pill").textContent)
        .toMatch(/KARAK CAFE/);
    // Backwards-compat alias for the legacy probe path.
    expect(screen.getByTestId("scratch-foil-canvas")).toBeInTheDocument();
    // Brand flows to --brand.
    const stage = screen.getByTestId("scratch-card-game");
    expect(stage.getAttribute("style")).toMatch(/--brand/);
    expect(stage.getAttribute("style")).toMatch(/#ff2d95/i);
  });

  test("foil layer carries the silver/charcoal gradient background", () => {
    render(<ScratchCardGame config={{ type: "scratch_card" }}
                onSubmit={() => {}} submitting={false}
                result={null} brand="#22c55e" />);
    const foil = screen.getByTestId("scratch-foil-layer");
    // jsdom's CSS parser rejects multi-layer backgroundImage strings
    // so `style.backgroundImage` reads as empty in tests.  Real
    // browsers render the gradient correctly (verified live in
    // Playwright); the deterministic Jest anchor is the
    // `data-foil-bg` attribute that mirrors the foil signature.
    const bg = foil.getAttribute("data-foil-bg") || "";
    expect(bg).toMatch(/#c0c0c0/i);
    expect(bg).toMatch(/#9a9a9a/i);
    expect(bg).toMatch(/silver-gradient/);
    expect(bg).toMatch(/diagonal-stripes/);
    // Mask-image initialization (deterministic in jsdom because it's
    // a single-layer linear-gradient).
    const mask = foil.style.maskImage || foil.style.webkitMaskImage || "";
    expect(mask).toMatch(/linear-gradient\(/);
  });

  test("first pointerdown hides the hint pill", () => {
    render(<ScratchCardGame config={{ type: "scratch_card" }}
                onSubmit={() => {}} submitting={false}
                result={null} brand="#22c55e" />);
    expect(screen.getByTestId("scratch-hint")).toBeInTheDocument();
    const foil = screen.getByTestId("scratch-foil-layer");
    act(() => {
      fireEvent.mouseDown(foil, { clientX: 100, clientY: 100, buttons: 1 });
    });
    expect(screen.queryByTestId("scratch-hint")).toBeNull();
  });

  test("dragging across enough points fires onSubmit exactly once " +
              "with scratched_pct >= 0.6", () => {
    jest.useFakeTimers();
    const submit = jest.fn();
    render(<ScratchCardGame config={{ type: "scratch_card" }}
                onSubmit={submit} submitting={false}
                result={null} brand="#ff2d95" />);
    const foil = screen.getByTestId("scratch-foil-layer");

    // 35 widely-spaced points → ~35 dots × π*40² ≈ 175,929 px coverage
    // on a 600×400 (240,000 px²) stage = ~73% > 60% threshold.
    act(() => {
      fireEvent.mouseDown(foil, { clientX: 30, clientY: 30, buttons: 1 });
    });
    const grid = [];
    for (let y = 30; y <= 370; y += 60) {
      for (let x = 30; x <= 570; x += 60) {
        grid.push([x, y]);
      }
    }
    act(() => {
      for (const [x, y] of grid) {
        fireEvent.mouseMove(foil, { clientX: x, clientY: y, buttons: 1 });
      }
    });
    // Foil layer now carries the "revealed" class (hidingFoil=true).
    expect(foil.className).toMatch(/revealed/);

    // The 400ms fade timeout fires the parent onSubmit.
    act(() => { jest.advanceTimersByTime(500); });
    expect(submit).toHaveBeenCalledTimes(1);
    const arg = submit.mock.calls[0][0];
    expect(arg).toMatchObject({ scratched_pct: expect.any(Number) });
    expect(arg.scratched_pct).toBeGreaterThanOrEqual(0.6);

    // Further moves after submit are no-ops (submit still called once).
    act(() => {
      for (let i = 0; i < 10; i++) {
        fireEvent.mouseMove(foil,
                                              { clientX: 100 + i, clientY: 200, buttons: 1 });
      }
      jest.advanceTimersByTime(1000);
    });
    expect(submit).toHaveBeenCalledTimes(1);
    jest.useRealTimers();
  });

  test("mask-image style grows as the user scratches", () => {
    render(<ScratchCardGame config={{ type: "scratch_card" }}
                onSubmit={() => {}} submitting={false}
                result={null} brand="#ff2d95" />);
    const foil = screen.getByTestId("scratch-foil-layer");
    const startMask = foil.getAttribute("style").match(
      /mask-image:\s*([^;]+);/i,
    )[1].trim();

    act(() => {
      fireEvent.mouseDown(foil, { clientX: 50, clientY: 50, buttons: 1 });
      fireEvent.mouseMove(foil, { clientX: 200, clientY: 100, buttons: 1 });
      fireEvent.mouseMove(foil, { clientX: 400, clientY: 200, buttons: 1 });
    });

    const afterMask = foil.getAttribute("style").match(
      /mask-image:\s*([^;]+);/i,
    )[1].trim();
    expect(afterMask.length).toBeGreaterThan(startMask.length);
    // After 3 dots we expect at least 3 radial-gradient holes.
    expect((afterMask.match(/radial-gradient/g) || []).length)
        .toBeGreaterThanOrEqual(3);
    // Coverage counter (data attribute) reflects point count.
    expect(Number(foil.getAttribute("data-foil-points"))).toBeGreaterThanOrEqual(3);
  });

  test("losing result still renders prize layer + 'Better luck' note", () => {
    render(<ScratchCardGame
                config={{ type: "scratch_card",
                                  prize_preview: { title: "Try again", value: "" } }}
                onSubmit={() => {}} submitting={false}
                result={{ result: "lose",
                                  prize: { title: "Try again", value: "" } }}
                brand="#22c55e" />);
    expect(screen.getByTestId("scratch-prize-layer")).toBeInTheDocument();
    expect(screen.getByTestId("scratch-prize-title").textContent)
        .toMatch(/Try again/);
    expect(screen.getByText(/Better luck next time/i))
        .toBeInTheDocument();
  });
});
