import { createRoot } from "react-dom/client";
import { MotionConfig } from "framer-motion";
import App from "./App.tsx";
import "./index.css";

// reducedMotion="user": index.css stills CSS animation under
// prefers-reduced-motion, but Framer Motion drives its own from JS and ignored
// that setting. With this, movement is dropped and fades are kept.
createRoot(document.getElementById("root")!).render(
  <MotionConfig reducedMotion="user">
    <App />
  </MotionConfig>
);
