import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { MetricCatalogProvider } from "./MetricCatalogContext";
import { ApiAuthenticationGate } from "./components/ApiAuthenticationGate";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ApiAuthenticationGate>
      <MetricCatalogProvider>
        <App />
      </MetricCatalogProvider>
    </ApiAuthenticationGate>
  </React.StrictMode>,
);
