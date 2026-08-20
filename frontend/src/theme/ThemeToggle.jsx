// Theme toggle (sun / moon). Used in the top bar and Me → Settings.
import React from "react";
import { Sun, Moon } from "lucide-react";
import { useTheme } from "./useTheme";

export default function ThemeToggle({ className = "" }) {
  const { theme, toggle } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      data-testid="theme-toggle"
      data-theme-state={theme}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Light theme" : "Dark theme"}
      className={[
        "w-10 h-10 grid place-items-center rounded-full",
        "text-text-secondary hover:text-text-primary",
        "hover:bg-[var(--bg-glass)] transition-colors duration-150",
        className,
      ].join(" ")}
    >
      {isDark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
