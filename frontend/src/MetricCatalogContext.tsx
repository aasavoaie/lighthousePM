import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { apiClient } from "./api/client";
import {
  fallbackMetricCatalog,
  resolveMetricCatalog,
  type MetricCatalogView,
} from "./metricCatalog";

const MetricCatalogContext = createContext<MetricCatalogView>(fallbackMetricCatalog);
let catalogRequest: ReturnType<typeof apiClient.getMetricCatalog> | null = null;

function loadMetricCatalog() {
  catalogRequest ??= apiClient.getMetricCatalog().catch((error: unknown) => {
    catalogRequest = null;
    throw error;
  });
  return catalogRequest;
}

export function MetricCatalogProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<MetricCatalogView>(fallbackMetricCatalog);

  useEffect(() => {
    let isActive = true;
    void loadMetricCatalog()
      .then((response) => {
        if (isActive) {
          setCatalog(resolveMetricCatalog(response));
        }
      })
      .catch(() => {
        if (isActive) {
          setCatalog(fallbackMetricCatalog);
        }
      });
    return () => {
      isActive = false;
    };
  }, []);

  return <MetricCatalogContext.Provider value={catalog}>{children}</MetricCatalogContext.Provider>;
}

export function useMetricCatalog() {
  return useContext(MetricCatalogContext);
}
