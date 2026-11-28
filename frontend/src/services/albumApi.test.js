// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchAlbumState, setSelectedUserSlug } from "./albumApi";

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("explicit album-state profile selection", () => {
  it("fails without making a request when no profile is selected", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(fetchAlbumState()).rejects.toThrow("Select a profile");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uses the selected profile route", async () => {
    setSelectedUserSlug("listener");
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    vi.stubGlobal("fetch", fetch);
    await fetchAlbumState();
    expect(fetch).toHaveBeenCalledWith("/api/users/listener/album-state", expect.any(Object));
  });
});
