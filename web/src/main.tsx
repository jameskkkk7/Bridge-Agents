import { createRoot } from "react-dom/client";
import "@fontsource-variable/kumbh-sans";
import "@fontsource-variable/noto-sans-sc";
import "@fontsource-variable/roboto-mono";
import App from "./App";
import { LanguageProvider } from "./i18n";
import { ThemeProvider } from "./theme";
import "./styles.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("root element missing");
}
createRoot(container).render(
  <ThemeProvider>
    <LanguageProvider>
      <App />
    </LanguageProvider>
  </ThemeProvider>,
);
