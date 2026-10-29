import type { Config } from "tailwindcss";

// Channel tokens support Tailwind opacity modifiers without losing theme identity.
const token = (name: string) => `rgb(var(--${name}-rgb) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Token-driven palette (CSS variables defined in styles/index.css)
        canvas: token("canvas"),
        surface: {
          DEFAULT: token("surface"),
          2: token("surface-2"),
          3: token("surface-3"),
        },
        line: {
          DEFAULT: token("border"),
          strong: token("border-strong"),
        },
        content: {
          DEFAULT: token("text"),
          muted: token("text-muted"),
          subtle: token("text-subtle"),
        },
        accent: {
          DEFAULT: token("accent"),
          strong: token("accent-strong"),
          fg: token("accent-fg"),
          soft: token("accent-soft"),
          // legacy per-industry refs kept for any stragglers
          fashion: "#e11d74",
          electronics: "#0891b2",
          pharma: "#059669",
          primary: token("accent"),
        },
        ink: {
          900: "#05060A",
          800: "#0B0D14",
          700: "#11141C",
          600: "#1A1F2B",
          500: "#252B3B",
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        display: ['"Space Grotesk"', '"IBM Plex Sans"', "sans-serif"],
        heading: ['"Space Grotesk"', '"IBM Plex Sans"', "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      transitionDuration: { fast: "var(--dur-fast)", base: "var(--dur)" },
      transitionTimingFunction: { standard: "var(--ease)" },
      borderRadius: {
        xl: "var(--radius-sm)",
        "2xl": "var(--radius)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        DEFAULT: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
      animation: {
        "fade-in": "fade-slide-up 0.4s ease-out both",
        "slide-up": "slide-up-fade 0.4s ease-out both",
        shimmer: "shimmer 1.6s linear infinite",
      },
      backgroundImage: {
        "gradient-accent":
          "linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%)",
      },
    },
  },
  plugins: [],
} satisfies Config;
