import { StrictMode } from "react"
import { createRoot, hydrateRoot } from "react-dom/client"

import App from "./App"
import "./index.css"

const container = document.getElementById("root")

if (!container) {
  throw new Error("missing #root element")
}

const app = (
  <StrictMode>
    <App />
  </StrictMode>
)

if (container.hasChildNodes()) {
  hydrateRoot(container, app)
} else {
  createRoot(container).render(app)
}
