// Renders the RadioLife Shop screens INSIDE the legacy AppShell so the
// left sidebar + top bar + look-and-feel stay put (no full-screen takeover).
// The dark theme (matching the legacy site) is applied via .rl-shop-inshell.
import React from "react";
import { useLocation } from "react-router-dom";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { screenFor } from "./RadioLifeOverlay";
import "./layout/shop-desktop-dark.css";

export default function ShopInShell() {
  const { pathname } = useLocation();
  const variant = useDesignVariant();
  // In the RadioLife "new look", the full-screen RadioLifeOverlay already
  // renders the shop — skip the in-shell copy to avoid a duplicate mount
  // (double component state + strict-mode/testid clashes).
  if (variant === "radiolife") return null;
  const Screen = screenFor(pathname);
  if (!Screen) return null;
  return (
    <div
      data-testid="rl-shop-inshell"
      className="rl-root rl-shop-desktop-dark rl-shop-inshell mx-auto w-full max-w-md lg:max-w-6xl">
      <Screen />
    </div>
  );
}
