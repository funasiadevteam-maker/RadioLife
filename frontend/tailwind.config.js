/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    screens: {
      sm: "640px",
      md: "768px",
      lg: "1024px",
      xl: "1280px",
      "2xl": "1536px",
    },
    extend: {
      colors: {
        // Phase 15a — design tokens (also exposed as CSS vars in index.css).
        "bg-base":     "var(--bg-base)",
        "bg-elevated": "var(--bg-elevated)",
        "bg-glass":    "var(--bg-glass)",
        "accent-electric": "var(--accent-electric)",
        "accent-magenta":  "var(--accent-magenta)",
        "accent-gold":     "var(--accent-gold)",
        "accent-success":  "var(--accent-success)",
        "accent-live":     "var(--accent-live)",
        "text-primary":   "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",

        // Legacy shadcn tokens kept for existing components.
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        chart: {
          1: "hsl(var(--chart-1))",
          2: "hsl(var(--chart-2))",
          3: "hsl(var(--chart-3))",
          4: "hsl(var(--chart-4))",
          5: "hsl(var(--chart-5))",
        },
      },
      borderRadius: {
        // Phase 15a — specific radii from the spec.
        "token-md":   "12px",
        "token-card": "20px",
        "token-hero": "28px",
        // Legacy mappings.
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        display: ["'Space Grotesk'", "ui-sans-serif", "system-ui",
                      "sans-serif"],
        sans:    ["Inter", "ui-sans-serif", "system-ui", "-apple-system",
                      "Segoe UI", "Roboto", "sans-serif"],
        mono:    ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular",
                      "Menlo", "monospace"],
      },
      letterSpacing: {
        "display-tight": "-0.02em",
      },
      boxShadow: {
        card:      "0 2px 8px rgba(0,0,0,0.4), 0 8px 32px rgba(0,0,0,0.25)",
        "card-hover": "0 6px 16px rgba(0,0,0,0.5), 0 18px 48px rgba(0,0,0,0.35)",
        glass:     "inset 0 0 0 1px rgba(255,255,255,0.08)",
      },
      backdropBlur: {
        glass: "20px",
      },
      transitionTimingFunction: {
        out150: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        pulseLive: {
          "0%,100%": { opacity: "1", transform: "scale(1)" },
          "50%":     { opacity: "0.55", transform: "scale(1.15)" },
        },
        fadeUp: {
          "0%":   { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "live-dot": "pulseLive 1.4s ease-in-out infinite",
        "fade-up":  "fadeUp 200ms cubic-bezier(0.16,1,0.3,1) both",
      },
    },
  },
  plugins: [],
};
