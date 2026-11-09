import { fileURLToPath } from "node:url";

// The Tailwind config is named by path, not looked up from the working directory, so
// the app builds the same whether Vite is started inside frontend/ or from elsewhere.
export default {
  plugins: {
    tailwindcss: { config: fileURLToPath(new URL("./tailwind.config.ts", import.meta.url)) },
    autoprefixer: {},
  },
};
