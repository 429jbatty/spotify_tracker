import { describe, expect, it } from "vitest";
import {
  connectionSearchProgress,
  connectionSearchResult,
} from "./connectionSearchStatus";

describe("connection search status", () => {
  it("explains a long-running foreground search with elapsed time", () => {
    expect(connectionSearchProgress(7)).toEqual({
      detail: "This library search is taking longer than usual.",
      label: "Searching your credit network… 7s",
    });
  });

  it("does not present a time-limited search as a no-path result", () => {
    expect(connectionSearchResult({
      search_limited_reason: "time_limit",
      search_time_limit_ms: 20_000,
    })).toEqual({
      detail: "No path was confirmed before the 20-second search limit. Try another pair or come back later.",
      title: "Search limit reached",
    });
  });

  it("explains when a path is returned before the time-limited search finishes", () => {
    expect(connectionSearchResult({
      best_path: { hop_count: 3 },
      search_limited_reason: "time_limit",
    })).toEqual({
      detail: "A path was confirmed, but the time limit was reached before every alternative could be checked.",
      title: "Indirect credit path",
    });
  });

  it("explains when the bounded result set is full", () => {
    expect(connectionSearchResult({
      best_path: { hop_count: 1 },
      search_limited_reason: "result_limit",
    })).toEqual({
      detail: "The strongest paths found within the result limit are shown.",
      title: "Direct shared credits",
    });
  });

  it("explains deterministic work limits without graph terminology", () => {
    expect(connectionSearchResult({
      search_limited_reason: "edge_limit",
    })).toEqual({
      detail: "This library is highly connected, so the search stopped before every route could be checked. Try another pair or come back later.",
      title: "Search limit reached",
    });
  });
});
