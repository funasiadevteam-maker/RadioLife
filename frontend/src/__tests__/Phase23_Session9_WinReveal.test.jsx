// Phase 23 Session 9 — WinReveal component contract tests.
//
// WinReveal is dropped in verbatim from the user's uploaded artifact;
// these tests pin the visible behavior (copy chip, save-to-wallet,
// double-click guard, retry-on-error) so future changes don't drift
// the listener win surface.
import React from "react";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import WinReveal from "@/components/WinReveal";
import * as playApi from "@/components/playApi";

// Mock the playApi.saveToWallet network call.
jest.mock("@/components/playApi", () => ({
  ...jest.requireActual("@/components/playApi"),
  saveToWallet: jest.fn(),
}));


const winOutcome = {
  playId: "ply_abc123",
  won: true,
  prizeId: "coffee",
  prizeTitle: "Free Latte",
  coupon: { code: "BIGFM-AB12CD34", redeemUrl: "/redeem/BIGFM-AB12CD34" },
  balance: 250,
  playedAt: "2026-06-07T00:00:00Z",
};

const loseOutcome = {
  playId: "ply_xyz789",
  won: false, prizeId: null, prizeTitle: null,
  coupon: null, balance: 200, playedAt: "2026-06-07T00:00:00Z",
};


describe("Phase 23 Session 9 — WinReveal", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // jsdom doesn't ship clipboard by default
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: jest.fn(() => Promise.resolve()) },
      writable: true, configurable: true,
    });
  });

  test("renders win state with prize title, coupon code, redeem link",
            () => {
    render(<WinReveal outcome={winOutcome} onPlayAgain={() => {}} />);
    expect(screen.getByText("Free Latte")).toBeInTheDocument();
    expect(screen.getByText("BIGFM-AB12CD34")).toBeInTheDocument();
    expect(screen.getByText(/View .*redeem/i))
      .toHaveAttribute("href", "/redeem/BIGFM-AB12CD34");
    expect(screen.getByText(/Save to Wallet/i)).toBeInTheDocument();
  });

  test("renders loss state with Try Again button", () => {
    const onAgain = jest.fn();
    render(<WinReveal outcome={loseOutcome} onPlayAgain={onAgain} />);
    expect(screen.getByText(/so close/i)).toBeInTheDocument();
    expect(screen.queryByText(/Save to Wallet/i)).toBeNull();
    fireEvent.click(screen.getByText(/Try Again/i));
    expect(onAgain).toHaveBeenCalledTimes(1);
  });

  test("copy coupon chip writes to clipboard + flips to COPIED ✓",
            async () => {
    render(<WinReveal outcome={winOutcome} onPlayAgain={() => {}} />);
    fireEvent.click(screen.getByText("BIGFM-AB12CD34"));
    await waitFor(() => {
      expect(navigator.clipboard.writeText)
        .toHaveBeenCalledWith("BIGFM-AB12CD34");
    });
    await waitFor(() => {
      expect(screen.getByText(/COPIED/)).toBeInTheDocument();
    });
  });

  test("Save to Wallet → Saving… → Saved to Wallet ✓", async () => {
    let resolveSave;
    playApi.saveToWallet.mockImplementation(
      () => new Promise((res) => { resolveSave = res; }));

    render(<WinReveal outcome={winOutcome} onPlayAgain={() => {}} />);
    const btn = screen.getByText(/Save to Wallet/i);
    fireEvent.click(btn);
    expect(await screen.findByText(/Saving/i)).toBeInTheDocument();

    await act(async () => { resolveSave({ walletItemId: "wi_1" }); });
    expect(await screen.findByText(/Saved to Wallet/i)).toBeInTheDocument();
    expect(playApi.saveToWallet).toHaveBeenCalledTimes(1);
    expect(playApi.saveToWallet).toHaveBeenCalledWith("ply_abc123");
  });

  test("double-click Save → only one saveToWallet call fired", async () => {
    let resolveSave;
    playApi.saveToWallet.mockImplementation(
      () => new Promise((res) => { resolveSave = res; }));

    render(<WinReveal outcome={winOutcome} onPlayAgain={() => {}} />);
    const btn = screen.getByText(/Save to Wallet/i);
    fireEvent.click(btn);
    fireEvent.click(btn);
    fireEvent.click(btn);
    // Only one network call — second/third are blocked by the
    // `wallet === "saving"` guard inside WinReveal.
    expect(playApi.saveToWallet).toHaveBeenCalledTimes(1);
    await act(async () => { resolveSave({ walletItemId: "wi_1" }); });
  });

  test("Save error → Retry save state, click again succeeds", async () => {
    playApi.saveToWallet
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce({ walletItemId: "wi_2" });

    render(<WinReveal outcome={winOutcome} onPlayAgain={() => {}} />);
    fireEvent.click(screen.getByText(/Save to Wallet/i));
    expect(await screen.findByText(/Retry save/i)).toBeInTheDocument();
    expect(await screen.findByText(/Couldn't save/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Retry save/i));
    expect(await screen.findByText(/Saved to Wallet/i)).toBeInTheDocument();
    expect(playApi.saveToWallet).toHaveBeenCalledTimes(2);
  });
});
