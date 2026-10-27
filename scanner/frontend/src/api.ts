import type { NewsItem, ScanResult, ScanSettings, Universe } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  universes: () => request<Universe[]>("/api/universes"),
  scan: (settings: ScanSettings, refresh = false) =>
    request<ScanResult>("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...settings, refresh }),
    }),
  news: (symbol: string) =>
    request<{ symbol: string; items: NewsItem[] }>(`/api/news/${encodeURIComponent(symbol)}`),
};
