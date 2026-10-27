import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "#26313c", input: "#26313c", ring: "#42e3c2",
        background: "#080d13", foreground: "#dce6ee",
        primary: { DEFAULT: "#42e3c2", foreground: "#071611" },
        secondary: { DEFAULT: "#182530", foreground: "#dce6ee" },
        destructive: { DEFAULT: "#ff6977", foreground: "#ffffff" },
        muted: { DEFAULT: "#121c26", foreground: "#8394a5" },
        accent: { DEFAULT: "#182530", foreground: "#dce6ee" },
      },
      borderRadius: { lg: "6px", md: "4px", sm: "3px" },
    },
  },
  plugins: [],
} satisfies Config;
