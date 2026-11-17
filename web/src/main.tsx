import { createRoot } from "react-dom/client";
import App from "./App";
import { LanguageProvider } from "./i18n";
import "./styles.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("root element missing");
}
createRoot(container).render(
  <LanguageProvider>
    <App />
  </LanguageProvider>,
);
