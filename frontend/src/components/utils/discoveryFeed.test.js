import { describe, expect, it } from "vitest";
import { buildDiscoveryFeed } from "./discoveryFeed";

const NOW = new Date(2026, 5, 20, 18, 0, 0);

function localDate(monthIndex, day, hour = 12, year = 2026) {
  return new Date(year, monthIndex, day, hour, 0, 0).toISOString();
}

function album({ key, artist = "Artist", listens }) {
  return {
    album_key: key,
    artist,
    id: key,
    name: key,
    listen_history: listens,
  };
}

describe("buildDiscoveryFeed", () => {
  it("includes a replay in the selected range when discovery predates the range", () => {
    const result = buildDiscoveryFeed(
      [
        album({
          key: "known",
          listens: [localDate(5, 1), localDate(5, 18)],
        }),
      ],
      "7d",
      { now: NOW }
    );

    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      album_key: "known",
      discoveredInRange: false,
      discoveryLabel: null,
      highlightDiscovery: false,
      inRangeListenCount: 1,
      latestInRangeListen: localDate(5, 18),
    });
  });

  it("collapses multiple in-range listens and sorts by the latest timestamp", () => {
    const result = buildDiscoveryFeed(
      [
        album({
          key: "older-latest",
          artist: "B Artist",
          listens: [localDate(5, 17), localDate(5, 18)],
        }),
        album({
          key: "newer-latest",
          artist: "A Artist",
          listens: [localDate(5, 16), localDate(5, 19, 20)],
        }),
      ],
      "7d",
      { now: NOW }
    );

    expect(result.map((item) => item.album_key)).toEqual([
      "newer-latest",
      "older-latest",
    ]);
    expect(result[0].inRangeListenCount).toBe(2);
    expect(result[0].latestInRangeListen).toBe(localDate(5, 19, 20));
  });

  it("marks first-time listens as new discoveries", () => {
    const result = buildDiscoveryFeed(
      [
        album({
          key: "new-album",
          listens: [localDate(5, 20)],
        }),
      ],
      "7d",
      { now: NOW }
    );

    expect(result[0]).toMatchObject({
      discoveredInRange: true,
      discoveryLabel: "New discovery",
      firstListenDate: localDate(5, 20),
      highlightDiscovery: true,
    });
  });

  it("highlights a fresh discovery even when the latest in-range listen is a replay", () => {
    const result = buildDiscoveryFeed(
      [
        album({
          key: "fresh-replay",
          listens: [localDate(5, 16), localDate(5, 20)],
        }),
      ],
      "7d",
      { now: NOW }
    );

    expect(result[0]).toMatchObject({
      discoveredInRange: true,
      discoveryLabel: "Discovered Jun 16, 2026",
      highlightDiscovery: true,
      inRangeListenCount: 2,
      latestInRangeListen: localDate(5, 20),
    });
  });

  it("shows older discoveries in broad ranges without the strong highlight", () => {
    const result = buildDiscoveryFeed(
      [
        album({
          key: "older-discovery",
          listens: [localDate(8, 20, 12, 2025), localDate(5, 20)],
        }),
      ],
      "1y",
      { now: NOW }
    );

    expect(result[0]).toMatchObject({
      discoveredInRange: true,
      discoveryLabel: "Discovered Sep 20, 2025",
      highlightDiscovery: false,
      inRangeListenCount: 2,
      latestInRangeListen: localDate(5, 20),
    });
  });

  it("highlights a discovery labeled as new in a broad range", () => {
    const result = buildDiscoveryFeed(
      [
        album({
          key: "older-new-discovery",
          listens: [localDate(8, 20, 12, 2025)],
        }),
      ],
      "1y",
      { now: NOW }
    );

    expect(result[0]).toMatchObject({
      discoveredInRange: true,
      discoveryLabel: "New discovery",
      highlightDiscovery: true,
    });
  });

  it("excludes albums with no listens in the selected range", () => {
    const result = buildDiscoveryFeed(
      [
        album({
          key: "old-only",
          listens: [localDate(4, 1), localDate(5, 1)],
        }),
        album({
          key: "invalid-only",
          listens: ["not-a-date"],
        }),
      ],
      "7d",
      { now: NOW }
    );

    expect(result).toEqual([]);
  });
});
