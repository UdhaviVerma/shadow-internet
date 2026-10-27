import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("passes the Clerk token only as an authorization header", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await api("/api/workspace", async () => "synthetic-token");
    const headers = fetch.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer synthetic-token");
    expect(fetch.mock.calls[0][0]).not.toContain("synthetic-token");
  });
  it("surfaces API errors instead of fabricating data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Hourly scan limit reached" }), { status: 429 })));
    await expect(api("/api/scans", async () => null)).rejects.toThrow("Hourly scan limit reached");
  });
  it("reports non-JSON upstream failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("gateway unavailable", { status: 502 })));
    await expect(api("/api/demo", async () => null)).rejects.toThrow("502");
  });
});
