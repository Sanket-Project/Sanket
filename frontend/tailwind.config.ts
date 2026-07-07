import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Token-driven palette (CSS variables defined in styles/index.css)
        canvas: "var(--canvas)",
        surface: {
          DEFAULT: "var(--surface)",
          2: "var(--surface-2)",
          3: "var(--surface-3)",
        },
        line: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
        },
        content: {
          DEFAULT: "var(--text)",
          muted: "var(--text-muted)",
          subtle: "var(--text-subtle)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          strong: "var(--accent-strong)",
          fg: "var(--accent-fg)",
          soft: "var(--accent-soft)",
          // legacy per-industry refs kept for any stragglers
          fashion: "#e11d74",
          electronics: "#0891b2",
          pharma: "#059669",
          primary: "var(--accent)",
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
