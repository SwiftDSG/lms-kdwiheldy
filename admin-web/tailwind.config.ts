import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#f5f0ee",
          100: "#e8dcd8",
          200: "#d0b8b0",
          300: "#b08070",
          400: "#7a4a35",
          500: "#4e2a1c",
          600: "#311D15",
          700: "#241610",
          800: "#180f0b",
          900: "#0c0805",
        },
        success: "#03C583",
        danger:  "#FF9093",
        warning: "#FFD890",
        calm:    "#AED1F6",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "sans-serif"],
      },
      borderWidth: {
        "3": "3px",
      },
    },
  },
  plugins: [],
};

export default config;
