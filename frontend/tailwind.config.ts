import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#ffffff",
        surface: "#fafafa",
        foreground: "#1f1f1f",
        muted: "#747474",
        line: "#e8e8e8",
        accent: "#456a8d",
        accentSoft: "#eef3f7",
        warm: "#f3f4f6",
      },
      borderRadius: {
        xl: "0.75rem",
        "2xl": "1rem",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "'Segoe UI'", "'PingFang SC'", "'Microsoft YaHei'", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
