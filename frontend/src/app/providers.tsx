"use client";

/**
 * Client providers root (ARCHITECTURE.md §10.2). Hosts the React Query client
 * so server-component `layout.tsx` can stay server-side. The client is created
 * once per browser session via `useState`.
 */

import { useState, type ReactNode } from "react";

import { QueryClientProvider } from "@tanstack/react-query";

import { createQueryClient } from "@/lib/query/queryClient";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
