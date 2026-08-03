// Phase 15a — keyboard shortcut contract test.
//
// We mount the hook (mocking react-router-dom's useNavigate so we don't
// pull RR7's ESM build into Jest's CJS world), then fire keydown events
// on document.body and assert the documented window events dispatch.

import React from "react";
import { render, act, cleanup } from "@testing-library/react";

const navigateMock = jest.fn();
jest.mock("react-router-dom", () => ({
  // Define inline to satisfy jest's hoist rule; we still reach the outer
  // navigateMock via a lazy require of this module after mock setup.
  useNavigate: () => global.__navigateMock__,
}), { virtual: true });
global.__navigateMock__ = navigateMock;

// Imported AFTER the mock so the hook sees the mocked useNavigate.
const { useKeyboardShortcuts } = require("../useKeyboardShortcuts");

function Harness({ enabled = true }) {
  useKeyboardShortcuts({ enabled });
  return null;
}

function listen(name) {
  const calls = { count: 0 };
  const fn = () => { calls.count += 1; };
  window.addEventListener(name, fn);
  return { calls, remove: () => window.removeEventListener(name, fn) };
}

function fire(key, opts = {}) {
  act(() => {
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...opts })
    );
  });
}

afterEach(() => { cleanup(); navigateMock.mockReset(); });

describe("useKeyboardShortcuts (Phase 15a)", () => {
  test("`/` dispatches bigfm:shortcut:focus-search", () => {
    render(<Harness />);
    const l = listen("bigfm:shortcut:focus-search");
    fire("/");
    expect(l.calls.count).toBe(1);
    l.remove();
  });

  test("space dispatches bigfm:player:toggle", () => {
    render(<Harness />);
    const l = listen("bigfm:player:toggle");
    fire(" ");
    expect(l.calls.count).toBe(1);
    l.remove();
  });

  test("arrow keys dispatch player volup/voldown", () => {
    render(<Harness />);
    const up = listen("bigfm:player:volup");
    const down = listen("bigfm:player:voldown");
    fire("ArrowRight");
    fire("ArrowLeft");
    expect(up.calls.count).toBe(1);
    expect(down.calls.count).toBe(1);
    up.remove(); down.remove();
  });

  test("j / k dispatch list next/prev", () => {
    render(<Harness />);
    const next = listen("bigfm:list:next");
    const prev = listen("bigfm:list:prev");
    fire("j");
    fire("k");
    expect(next.calls.count).toBe(1);
    expect(prev.calls.count).toBe(1);
    next.remove(); prev.remove();
  });

  test.each([
    ["h", "home",   "/"],
    ["r", "radio",  "/radio"],
    ["p", "play",   "/play"],
    ["t", "trivia", "/trivia"],
    ["w", "wallet", "/wallet"],
    ["g", "games",  "/passport"],
    ["m", "map",    "/map"],
  ])("two-stroke g+%s dispatches bigfm:route:%s and navigates to %s", (k, ev, path) => {
    render(<Harness />);
    const l = listen(`bigfm:route:${ev}`);
    fire("g");
    fire(k);
    expect(l.calls.count).toBe(1);
    expect(navigateMock).toHaveBeenCalledWith(path);
    l.remove();
  });

  test("disabled=true never installs the listener", () => {
    render(<Harness enabled={false} />);
    const l = listen("bigfm:shortcut:focus-search");
    fire("/");
    expect(l.calls.count).toBe(0);
    l.remove();
  });

  test("typing inside an INPUT does not intercept `/`", () => {
    const { container } = render(
      <>
        <Harness />
        <input data-testid="probe-input" />
      </>
    );
    const input = container.querySelector('[data-testid="probe-input"]');
    input.focus();
    const l = listen("bigfm:shortcut:focus-search");
    act(() => {
      input.dispatchEvent(
        new KeyboardEvent("keydown", { key: "/", bubbles: true, cancelable: true })
      );
    });
    expect(l.calls.count).toBe(0);
    l.remove();
  });

  test("modifier keys are ignored", () => {
    render(<Harness />);
    const l = listen("bigfm:shortcut:focus-search");
    fire("/", { metaKey: true });
    fire("/", { ctrlKey: true });
    fire("/", { altKey: true });
    expect(l.calls.count).toBe(0);
    l.remove();
  });
});
