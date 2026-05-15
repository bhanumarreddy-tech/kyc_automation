import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

const rootEl = document.getElementById("root");
if (!rootEl) {
  document.body.innerHTML =
    "<p style=\"font-family:system-ui;padding:1rem\">Missing #root — check index.html.</p>";
} else {
  createRoot(rootEl).render(<App />);
}
