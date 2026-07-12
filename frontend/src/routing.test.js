import { describe, expect, it } from "vitest";
import {
  albumPath,
  formatLibrarySortParam,
  getActiveView,
  legacyRedirectPath,
  normalizeDiscoveryRange,
  parseLibrarySortParam,
  PROFILE_ROUTES,
  profilePath,
} from "./routing";

describe("routing helpers", () => {
  it("builds stable user-scoped profile routes", () => {
    expect(profilePath("jacob", PROFILE_ROUTES.discovery)).toBe("/jacob/discovery");
    expect(profilePath("jacob", PROFILE_ROUTES.library)).toBe("/jacob/library");
    expect(profilePath("jacob", PROFILE_ROUTES.releases)).toBe("/jacob/releases");
    expect(profilePath("jacob", PROFILE_ROUTES.connections)).toBe("/jacob/connections");
  });

  it("builds route-backed album detail paths", () => {
    expect(albumPath("jacob", 123)).toBe("/jacob/albums/123");
  });

  it("uses library as the active section for album detail routes", () => {
    expect(getActiveView("/jacob/albums/123")).toBe(PROFILE_ROUTES.library);
  });

  it("maps legacy profile paths to current routes", () => {
    expect(legacyRedirectPath("jacob", "albums")).toBe("/jacob/library");
    expect(legacyRedirectPath("jacob", "timeline")).toBe("/jacob/releases");
  });

  it("preserves discovery range query values when valid", () => {
    expect(normalizeDiscoveryRange("1y", ["7d", "30d", "1y", "all"])).toBe("1y");
    expect(normalizeDiscoveryRange("invalid", ["7d", "30d", "1y", "all"])).toBe("1y");
  });

  it("parses and formats library sort query values", () => {
    expect(parseLibrarySortParam("recent")).toEqual({
      sortBy: "latestListen",
      ascending: false,
    });
    expect(parseLibrarySortParam("oldest")).toEqual({
      sortBy: "latestListen",
      ascending: true,
    });
    expect(parseLibrarySortParam("name:asc")).toEqual({
      sortBy: "name",
      ascending: true,
    });
    expect(formatLibrarySortParam("latestListen", false)).toBe("recent");
    expect(formatLibrarySortParam("name", true)).toBe("name:asc");
  });
});
