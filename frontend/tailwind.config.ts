import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#f5f4ef",
        surface: "#fcfbf7",
        foreground: "#171717",
        muted: "#6f6a60",
        line: "#e8e2d6",
        accent: "#1f6feb",
        accentSoft: "#e8f0ff",
        warm: "#efe7d8",
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.5rem",
      },
      fontFamily: {
        sans: ["'Segoe UI'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      boxShadow: {
        panel: "0 18px 48px rgba(21, 24, 28, 0.06)",
      },
    },
  },
  plugins: [],
} satisfies Config;
