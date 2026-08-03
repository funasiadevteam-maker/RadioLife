// Phase 15b — audio bus contract. We mount the hook with mock callbacks,
// dispatch the `bigfm:player:*` / `bigfm:list:*` window events, and assert
// the right callback fired. Cleanup is asserted via re-mount + dispatch.

import React from "react";
import { render, act, cleanup } from "@testing-library/react";

const { useAudioBus, bumpVolume } = require("../useAudioBus");

function Harness({ handlers }) {
  useAudioBus(handlers);
  return null;
}

function fire(name, detail) {
  act(() => {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  });
}

afterEach(() => cleanup());

describe("useAudioBus (Phase 15b)", () => {
  test("bigfm:player:toggle calls onToggle", () => {
    const onToggle = jest.fn();
    render(<Harness handlers={{ onToggle }} />);
    fire("bigfm:player:toggle");
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  test("bigfm:player:volup / voldown call onVolUp / onVolDown", () => {
    const onVolUp = jest.fn();
    const onVolDown = jest.fn();
    render(<Harness handlers={{ onVolUp, onVolDown }} />);
    fire("bigfm:player:volup");
    fire("bigfm:player:voldown");
    expect(onVolUp).toHaveBeenCalledTimes(1);
    expect(onVolDown).toHaveBeenCalledTimes(1);
  });

  test("bigfm:list:next / prev call onListNext / onListPrev", () => {
    const onListNext = jest.fn();
    const onListPrev = jest.fn();
    render(<Harness handlers={{ onListNext, onListPrev }} />);
    fire("bigfm:list:next");
    fire("bigfm:list:prev");
    expect(onListNext).toHaveBeenCalledTimes(1);
    expect(onListPrev).toHaveBeenCalledTimes(1);
  });

  test("unmount removes the listeners (no leak)", () => {
    const onToggle = jest.fn();
    const { unmount } = render(<Harness handlers={{ onToggle }} />);
    unmount();
    fire("bigfm:player:toggle");
    expect(onToggle).not.toHaveBeenCalled();
  });

  test("missing handlers are tolerated (no error, no fire)", () => {
    render(<Harness handlers={{}} />);
    expect(() => fire("bigfm:player:toggle")).not.toThrow();
  });

  test("throwing handler does not break the listener", () => {
    const onToggle = jest.fn(() => { throw new Error("boom"); });
    const onVolUp = jest.fn();
    render(<Harness handlers={{ onToggle, onVolUp }} />);
    fire("bigfm:player:toggle");
    fire("bigfm:player:volup");
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onVolUp).toHaveBeenCalledTimes(1);
  });

  test("bumpVolume clamps to [0,1] and writes back to the element", () => {
    const el = { volume: 0.5 };
    expect(bumpVolume(el, 0.3)).toBeCloseTo(0.8);
    expect(el.volume).toBeCloseTo(0.8);
    expect(bumpVolume(el, 0.5)).toBe(1);   // clamp high
    expect(el.volume).toBe(1);
    bumpVolume(el, -2);
    expect(el.volume).toBe(0);             // clamp low
    expect(bumpVolume(null, 0.1)).toBeNull();
  });

  test("event detail is forwarded to the callback", () => {
    const onToggle = jest.fn();
    render(<Harness handlers={{ onToggle }} />);
    fire("bigfm:player:toggle", { source: "keyboard" });
    expect(onToggle).toHaveBeenCalledWith({ source: "keyboard" });
  });
});
