// Phase 36d Turn 3 — Lightning splits frontend tests.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

// Mock react-router-dom (v7 ESM).
jest.mock("react-router-dom", () => ({
  __esModule: true,
  Link:           ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  useNavigate: () => jest.fn(),
  useLocation: () => ({ pathname: "/" }),
  useParams:     () => ({ channel_id: "pch_test", ep_id: "pep_test" }),
}), { virtual: true });

// Mock axios — drive the resolved/save paths from each test.
const mockAxios = { get: jest.fn(), put: jest.fn(), patch: jest.fn(),
                                  delete: jest.fn(), post: jest.fn() };
jest.mock("axios", () => ({
  __esModule: true,
  default: mockAxios,
}));

const VALID_PK_A = "02" + "a".repeat(64);
const VALID_PK_B = "03" + "b".repeat(64);

beforeEach(() => {
  mockAxios.get.mockReset();
  mockAxios.put.mockReset();
  mockAxios.delete.mockReset();
});

describe("Phase 36d Turn 3 — Lightning splits", () => {
  test("editor running-total chip + Save gate reflect sum=100", async () => {
    mockAxios.get.mockResolvedValueOnce({data: {
      channel_id: "pch_test", episode_id: null,
      recipients: [
        {name: "Creator", type: "node", address: VALID_PK_A,
          split_pct: 60, fee_pct: 0},
        {name: "Platform", type: "node", address: VALID_PK_B,
          split_pct: 30, fee_pct: 0},
      ],
    }});
    const {LightningSplitsEditor} = require("../LightningSplitsEditor");
    render(<LightningSplitsEditor
      testIdPrefix="lightning"
      loadUrl="/api/x/load" saveUrl="/api/x/save"
      helperText="Help"
    />);
    await waitFor(() => screen.getByTestId("lightning-editor"));
    // 60 + 30 = 90 → Save disabled, chip red.
    const chip = screen.getByTestId("lightning-total-chip");
    expect(chip.textContent).toContain("90.0%");
    const save = screen.getByTestId("lightning-save");
    expect(save).toBeDisabled();
    // Bump row 1 split to 40 → total 100 → Save enabled.
    const split1 = screen.getByTestId("lightning-split-1");
    fireEvent.change(split1, {target: {value: "40"}});
    expect(screen.getByTestId("lightning-total-chip").textContent)
      .toContain("100.0%");
    expect(screen.getByTestId("lightning-save")).not.toBeDisabled();
  });

  test("editor row count + Add/Delete buttons mutate state", async () => {
    mockAxios.get.mockResolvedValueOnce({data: {recipients: [
      {name: "Solo", type: "node", address: VALID_PK_A,
        split_pct: 100, fee_pct: 0},
    ]}});
    const {LightningSplitsEditor} = require("../LightningSplitsEditor");
    render(<LightningSplitsEditor
      testIdPrefix="lightning"
      loadUrl="/api/x/load" saveUrl="/api/x/save"
    />);
    await waitFor(() => screen.getByTestId("lightning-row-0"));
    // Add row → mount a 2nd row in DOM.
    fireEvent.click(screen.getByTestId("lightning-add"));
    expect(screen.getByTestId("lightning-row-1")).toBeInTheDocument();
    // Push row 0 to 70% → total 70 → Save disables.
    fireEvent.change(screen.getByTestId("lightning-split-0"),
                                    {target: {value: "70"}});
    expect(screen.getByTestId("lightning-save")).toBeDisabled();
    // Delete the added row → only row 0 (70%) remains → still !=100, still disabled.
    fireEvent.click(screen.getByTestId("lightning-delete-1"));
    expect(screen.queryByTestId("lightning-row-1")).toBeNull();
    expect(screen.getByTestId("lightning-save")).toBeDisabled();
    // Bump row 0 back to 100 → Save re-enables.
    fireEvent.change(screen.getByTestId("lightning-split-0"),
                                    {target: {value: "100"}});
    expect(screen.getByTestId("lightning-save")).not.toBeDisabled();
  });
});
