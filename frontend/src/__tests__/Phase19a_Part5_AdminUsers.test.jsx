// Phase 19a Part 5 FRONTEND tests — /admin/users page.
//
// Covers minimum coverage requested by the dispatch:
//   1. Stats cards render with mock data
//   2. Table renders with mock users + correct badge colors per role/status
//   3. Filter bar wiring triggers correct API calls (role + search debounce)
//   4. ChangeRoleModal disables confirm when target is self
//   5. DeactivateModal requires non-empty reason (>=5 chars)
//
// Mocks react-router-dom + AuthContext + axios (no real network).

import React from "react";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("react-router-dom", () => ({
  __esModule: true,
  Link:              ({ children, to, ...rest }) => <a href={to} {...rest}>{children}</a>,
  useNavigate:      () => jest.fn(),
  useLocation:      () => ({ pathname: "/admin/users" }),
  useParams:        () => ({}),
}), { virtual: true });

let mockAdmin = {
  user_id: "user_admin1", role: "admin", email: "admin@bigfm.dubai",
};
jest.mock("@/AuthContext", () => ({
  __esModule: true,
  useAuth: () => ({ user: mockAdmin, loading: false }),
  API: "http://localhost:8001/api",
}));

const mockCalls = { get: [], post: [], patch: [] };
let mockResponses = {};
jest.mock("axios", () => ({
  __esModule: true,
  default: {
    get:   (url, opts) => { mockCalls.get.push([url, opts]);
                            const base = url.split("?")[0];
                            const r = mockResponses["GET " + base];
                            if (r) return Promise.resolve({ data: r });
                            return Promise.resolve({ data: { items: [] } }); },
    post:  (url, body, opts) => { mockCalls.post.push([url, body, opts]);
                                  return Promise.resolve({ data: { ok: true } }); },
    patch: (url, body, opts) => { mockCalls.patch.push([url, body, opts]);
                                  return Promise.resolve({ data: { ok: true } }); },
  },
}));

const baseStats = {
  total: 1024,
  by_role: { admin: 3, creator: 12, listener: 1000, business_partner: 9 },
  by_status: { active: 1000, inactive: 20, suspended: 4 },
  new_signups_7d: 14,
  deactivations_7d: 2,
};

const sampleUser = (over = {}) => ({
  user_id: over.user_id || "user_abc",
  email:   over.email   || "u@example.com",
  name:    over.name    || "U Name",
  role:    over.role    || "listener",
  status:  over.status  || "active",
  created_at:    "2026-01-01T00:00:00Z",
  last_login_at: "2026-02-01T00:00:00Z",
  ...over,
});

function setupResponses({ stats = baseStats, users = [] } = {}) {
  mockCalls.get.length = 0;
  mockCalls.post.length = 0;
  mockCalls.patch.length = 0;
  mockResponses = {
    "GET http://localhost:8001/api/admin/users/stats": stats,
    "GET http://localhost:8001/api/admin/users":
      { items: users, next_cursor: null, limit: 25 },
    "GET http://localhost:8001/api/admin/users/audit-log":
      { items: [], next_cursor: null, limit: 50 },
  };
}

describe("Phase 19a Part 5 — AdminUsers list", () => {
  beforeEach(() => { jest.useFakeTimers(); });
  afterEach(() => { jest.useRealTimers(); });

  test("renders 4 stats cards with the right counts", async () => {
    setupResponses();
    const AdminUsers = require("@/AdminUsers").default;
    await act(async () => { render(<AdminUsers />); });
    await waitFor(() => expect(screen.getByTestId("stat-total-users"))
        .toHaveTextContent("1,024"));
    expect(screen.getByTestId("stat-active-users")).toHaveTextContent("1,000");
    expect(screen.getByTestId("stat-inactive-users")).toHaveTextContent("24");
    expect(screen.getByTestId("stat-creator-users")).toHaveTextContent("12");
  });

  test("renders user rows with role + status badges", async () => {
    setupResponses({ users: [
      sampleUser({ user_id: "u1", email: "alice@x.com", role: "creator" }),
      sampleUser({ user_id: "u2", email: "bob@x.com",
                            role: "listener", status: "inactive" }),
    ] });
    const AdminUsers = require("@/AdminUsers").default;
    await act(async () => { render(<AdminUsers />); });
    await waitFor(() => expect(screen.getByTestId("user-row-u1")).toBeInTheDocument());
    expect(screen.getByTestId("role-u1")).toHaveTextContent(/creator/i);
    expect(screen.getByTestId("status-u1")).toHaveTextContent(/active/i);
    expect(screen.getByTestId("role-u2")).toHaveTextContent(/listener/i);
    expect(screen.getByTestId("status-u2")).toHaveTextContent(/inactive/i);
  });

  test("role filter change triggers a refetch with ?role=", async () => {
    setupResponses({ users: [sampleUser()] });
    const AdminUsers = require("@/AdminUsers").default;
    await act(async () => { render(<AdminUsers />); });
    await waitFor(() => expect(screen.getByTestId("user-row-user_abc"))
        .toBeInTheDocument());
    await act(async () => {
      fireEvent.change(screen.getByTestId("filter-role"),
                                    { target: { value: "creator" } });
    });
    await waitFor(() => {
      const hit = mockCalls.get.find(([url]) =>
        url.startsWith("http://localhost:8001/api/admin/users?")
        && url.includes("role=creator"));
      expect(hit).toBeTruthy();
    });
  });

  test("debounced search waits 350ms and then refetches with ?search=", async () => {
    setupResponses({ users: [sampleUser()] });
    const AdminUsers = require("@/AdminUsers").default;
    await act(async () => { render(<AdminUsers />); });
    await waitFor(() => expect(screen.getByTestId("user-row-user_abc"))
        .toBeInTheDocument());
    await act(async () => {
      fireEvent.change(screen.getByTestId("filter-search"),
                                    { target: { value: "alice" } });
    });
    // Before debounce expires, no new fetch with search=
    const before = mockCalls.get.filter(([u]) => u.includes("search=")).length;
    expect(before).toBe(0);
    await act(async () => { jest.advanceTimersByTime(400); });
    await waitFor(() => {
      const after = mockCalls.get.find(([u]) => u.includes("search=alice"));
      expect(after).toBeTruthy();
    });
  });
});

describe("Phase 19a Part 5 — ChangeRoleModal safety rails", () => {
  test("self demotion disables Confirm", async () => {
    setupResponses();
    const { ChangeRoleModal } = require("@/AdminUsers");
    await act(async () => {
      render(<ChangeRoleModal
        user={{ user_id: "user_admin1", email: "admin@bigfm.dubai", role: "admin" }}
        currentAdminId="user_admin1" adminCount={3}
        onClose={() => {}} onSuccess={() => {}} />);
    });
    // First non-admin option is selected by default.
    expect(screen.getByTestId("warn-self")).toBeInTheDocument();
    expect(screen.getByTestId("confirm-role")).toBeDisabled();
  });

  test("last-admin demotion is blocked", async () => {
    setupResponses();
    const { ChangeRoleModal } = require("@/AdminUsers");
    await act(async () => {
      render(<ChangeRoleModal
        user={{ user_id: "user_only_admin", email: "only@x.com", role: "admin" }}
        currentAdminId="user_admin1" adminCount={1}
        onClose={() => {}} onSuccess={() => {}} />);
    });
    expect(screen.getByTestId("warn-last-admin")).toBeInTheDocument();
    expect(screen.getByTestId("confirm-role")).toBeDisabled();
  });

  test("valid role + reason >=5 chars enables Confirm", async () => {
    setupResponses();
    const { ChangeRoleModal } = require("@/AdminUsers");
    await act(async () => {
      render(<ChangeRoleModal
        user={{ user_id: "user_x", email: "x@x.com", role: "listener" }}
        currentAdminId="user_admin1" adminCount={3}
        onClose={() => {}} onSuccess={() => {}} />);
    });
    expect(screen.getByTestId("confirm-role")).toBeDisabled();
    await act(async () => {
      fireEvent.change(screen.getByTestId("reason-textarea"),
                                    { target: { value: "promote" } });
    });
    expect(screen.getByTestId("confirm-role")).not.toBeDisabled();
  });
});

describe("Phase 19a Part 5 — DeactivateModal", () => {
  test("requires non-empty 5+ char reason and blocks self-deactivate", async () => {
    setupResponses();
    const { DeactivateModal } = require("@/AdminUsers");
    await act(async () => {
      render(<DeactivateModal
        user={{ user_id: "user_admin1", email: "admin@x.com", role: "admin",
                    status: "active" }}
        currentAdminId="user_admin1" adminCount={3}
        onClose={() => {}} onSuccess={() => {}} />);
    });
    // Self-deactivate warning shown + button disabled even with reason filled.
    expect(screen.getByTestId("warn-self")).toBeInTheDocument();
    await act(async () => {
      fireEvent.change(screen.getByTestId("reason-textarea"),
                                    { target: { value: "valid reason text" } });
    });
    expect(screen.getByTestId("confirm-deactivate")).toBeDisabled();
  });

  test("non-self, valid 5+ char reason enables Deactivate", async () => {
    setupResponses();
    const { DeactivateModal } = require("@/AdminUsers");
    await act(async () => {
      render(<DeactivateModal
        user={{ user_id: "user_target", email: "t@x.com", role: "listener",
                    status: "active" }}
        currentAdminId="user_admin1" adminCount={3}
        onClose={() => {}} onSuccess={() => {}} />);
    });
    expect(screen.getByTestId("confirm-deactivate")).toBeDisabled();
    await act(async () => {
      fireEvent.change(screen.getByTestId("reason-textarea"),
                                    { target: { value: "abuse" } });
    });
    expect(screen.getByTestId("confirm-deactivate")).not.toBeDisabled();
  });
});
