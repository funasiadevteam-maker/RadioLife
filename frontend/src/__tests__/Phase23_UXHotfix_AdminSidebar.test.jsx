// Phase 23 UX-Hotfix B2 — admin sidebar context tests.
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import "@testing-library/jest-dom";

let mockUser = { user_id: "u1", role: "admin", email: "admin@bigfm.dubai" };
jest.mock("@/AuthContext", () => ({
  useAuth: () => ({ user: mockUser, loading: false }),
  API: "http://test",
}));

import AdminSidebar from "@/components/AdminSidebar";

function withRouter(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<AdminSidebar />} />
      </Routes>
    </MemoryRouter>);
}

describe("Phase 23 UX-Hotfix B2 — admin sidebar", () => {
  test("renders admin nav + 'Return to Home' on /admin/* when admin",
            () => {
    mockUser = { user_id: "u1", role: "admin" };
    withRouter("/admin/games-approval");
    expect(screen.getByTestId("admin-sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("admin-sidebar-return-home"))
      .toHaveAttribute("href", "/");
    expect(screen.getByText("Approval Queue")).toBeInTheDocument();
    expect(screen.getByText("Users")).toBeInTheDocument();
    expect(screen.getByText("Bulk Upload")).toBeInTheDocument();
  });

  test("hidden on listener routes", () => {
    mockUser = { user_id: "u1", role: "admin" };
    withRouter("/play-and-win");
    expect(screen.queryByTestId("admin-sidebar")).toBeNull();
  });

  test("hidden for non-admin users even on /admin/*", () => {
    mockUser = { user_id: "u1", role: "advertiser" };
    withRouter("/admin/games-approval");
    expect(screen.queryByTestId("admin-sidebar")).toBeNull();
  });

  test("hidden when no user is logged in", () => {
    mockUser = null;
    withRouter("/admin/games-approval");
    expect(screen.queryByTestId("admin-sidebar")).toBeNull();
  });
});
