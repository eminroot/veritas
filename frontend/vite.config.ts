import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // The backend the dev server forwards /v1 and /health to, so the app and the API share
  // one origin in development and need no CORS. Production does the same in nginx.conf.
  const env = loadEnv(mode, process.cwd(), "");
  const api = env.VERITAS_API_PROXY || "http://localhost:8000";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 8080,
      proxy: {
        "/v1": { target: api, changeOrigin: true },
        "/health": { target: api, changeOrigin: true },
      },
    },
    preview: {
      port: 8080,
      proxy: {
        "/v1": { target: api, changeOrigin: true },
        "/health": { target: api, changeOrigin: true },
      },
    },
    build: {
      // Off in production: source maps would serve the whole original source to every
      // visitor. Kept in development, where they are what makes debugging work.
      sourcemap: mode !== "production",
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ["react", "react-dom", "react-router-dom"],
            firebase: ["firebase/app", "firebase/auth"],
            motion: ["framer-motion"],
          },
        },
      },
    },
  };
});
