/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#090d18",
        panel: "#101625",
        surface: "#151e30",
        line: "#202b40",
        muted: "#8591a8",
        brand: "#8b7cff",
        mint: "#65e4b5",
      },
      boxShadow: {
        glow: "0 0 48px rgba(139, 124, 255, 0.14)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};
