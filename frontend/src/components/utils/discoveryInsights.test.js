import { describe, expect, it } from "vitest";
import { aggregateDiscoveryInsights } from "./discoveryInsights";

const NOW = new Date(2026, 5, 20, 18, 0, 0);

function localDate(monthIndex, day, hour = 12) {
  return new Date(2026, monthIndex, day, hour, 0, 0).toISOString();
}

function album({ key, artist, artistMbid, listens }) {
  return {
    album_key: key,
    artist,
    artist_mbid: artistMbid,
    name: key,
    listen_history: listens,
  };
}

describe("aggregateDiscoveryInsights", () => {
  it("counts every listen to an album discovered in the selected range as new to you", () => {
    const albums = {
      third: album({
        key: "artist two - debut",
        artist: "Artist Two",
        listens: [localDate(5, 17)],
      }),
      second: album({
        key: "artist one - follow-up",
        artist: "Artist One",
        listens: [localDate(5, 15)],
      }),
      first: album({
        key: "artist one - debut",
        artist: "Artist One",
        listens: [localDate(5, 14), localDate(5, 16)],
      }),
    };

    const result = aggregateDiscoveryInsights(albums, "7d", { now: NOW });

    expect(result.summary).toEqual({
      newToYou: 4,
      catalog: 0,
      totalListens: 4,
    });
    expect(result.buckets).toHaveLength(7);
    expect(result.buckets.map((bucket) => bucket.total)).toEqual([
      1, 1, 1, 1, 0, 0, 0,
    ]);
  });

  it("counts an in-window listen as catalog listening when discovery predates the window", () => {
    const albums = {
      known: album({
        key: "known - album",
        artist: "Known",
        listens: [localDate(5, 1), localDate(5, 18)],
      }),
    };

    const result = aggregateDiscoveryInsights(albums, "7d", { now: NOW });

    expect(result.baseline).toEqual({ albums: 1, artists: 1 });
    expect(result.summary).toEqual({
      newToYou: 0,
      catalog: 1,
      totalListens: 1,
    });
  });

  it("counts ten listens to an album discovered this week as new to you", () => {
    const result = aggregateDiscoveryInsights(
      {
        newAlbum: album({
          key: "artist - new album",
          artist: "Artist",
          listens: Array.from({ length: 10 }, (_, index) => localDate(5, 14, index)),
        }),
      },
      "7d",
      { now: NOW }
    );

    expect(result.summary).toEqual({
      newToYou: 10,
      catalog: 0,
      totalListens: 10,
    });
  });

  it("counts albums discovered at equal timestamps as new to you", () => {
    const sameTime = localDate(5, 19);
    const albums = {
      z: album({
        key: "z-album",
        artist: "Different Display Name",
        artistMbid: "shared-artist-id",
        listens: [sameTime],
      }),
      a: album({
        key: "a-album",
        artist: "Artist Name",
        artistMbid: "shared-artist-id",
        listens: [sameTime],
      }),
      spacing: album({
        key: "spacing-album",
        artist: "  CASED   ARTIST ",
        listens: [sameTime],
      }),
      normalized: album({
        key: "normalized-album",
        artist: "cased artist",
        listens: [sameTime],
      }),
    };

    const result = aggregateDiscoveryInsights(albums, "7d", { now: NOW });
    const populated = result.buckets.find((bucket) => bucket.total === 4);

    expect(populated.newToYou).toBe(4);
    expect(populated.catalog).toBe(0);
  });

  it("creates daily and weekly buckets including empty periods", () => {
    const albums = {
      one: album({
        key: "artist - album",
        artist: "Artist",
        listens: [localDate(3, 10), localDate(5, 20)],
      }),
    };

    const daily = aggregateDiscoveryInsights(albums, "7d", { now: NOW });
    const dailyMonth = aggregateDiscoveryInsights(albums, "30d", { now: NOW });
    const weekly = aggregateDiscoveryInsights(albums, "1y", { now: NOW });

    expect(daily.buckets).toHaveLength(7);
    expect(dailyMonth.buckets).toHaveLength(30);
    expect(weekly.buckets).toHaveLength(53);
    expect(weekly.buckets.every((bucket) => bucket.start.getDay() === 1)).toBe(true);
  });

  it("returns percentages that sum to 100 and cumulative catalog growth with a baseline", () => {
    const albums = {
      known: album({
        key: "known - first",
        artist: "Known",
        listens: [localDate(5, 1), localDate(5, 18)],
      }),
      newAlbum: album({
        key: "known - second",
        artist: "Known",
        listens: [localDate(5, 18, 13)],
      }),
      newArtist: album({
        key: "new - first",
        artist: "New",
        listens: [localDate(5, 18, 14)],
      }),
    };

    const result = aggregateDiscoveryInsights(albums, "7d", { now: NOW });
    const populated = result.buckets.find((bucket) => bucket.total === 3);

    expect(result.baseline).toEqual({ albums: 1, artists: 1 });
    expect(
      Object.values(populated.percentages).reduce((sum, value) => sum + value, 0)
    ).toBeCloseTo(100);
    expect(populated.catalogAlbums).toBe(3);
    expect(populated.catalogArtists).toBe(2);
    expect(populated.albumGrowth).toBe(2);
    expect(populated.artistGrowth).toBe(1);
  });

  it("handles empty input, invalid dates, and a single valid listen", () => {
    const empty = aggregateDiscoveryInsights({}, "7d", { now: NOW });
    const mixed = aggregateDiscoveryInsights(
      {
        one: album({
          key: "artist - album",
          artist: "Artist",
          listens: ["not-a-date", localDate(5, 20)],
        }),
      },
      "7d",
      { now: NOW }
    );

    expect(empty.buckets).toHaveLength(7);
    expect(empty.summary.totalListens).toBe(0);
    expect(empty.totalLifetimeListens).toBe(0);
    expect(mixed.summary).toEqual({
      newToYou: 1,
      catalog: 0,
      totalListens: 1,
    });
  });

  it("builds concentration, coverage, and artist-map insights", () => {
    const albums = {
      one: {
        ...album({
          key: "artist one - album",
          artist: "Artist One",
          listens: [localDate(5, 18), localDate(5, 19)],
        }),
        release_year: 2018,
      },
      two: {
        ...album({
          key: "artist two - album",
          artist: "Artist Two",
          listens: [localDate(5, 18, 13)],
        }),
        release_year: 1974,
      },
      undated: album({
        key: "undated - album",
        artist: "Undated",
        listens: [],
      }),
    };

    const result = aggregateDiscoveryInsights(albums, "7d", { now: NOW });

    expect(result.coverage).toEqual({ datedAlbums: 2, totalAlbums: 3 });
    expect(result.concentration.overallShare).toBe(100);
    expect(result.artistMap).toEqual([
      { albumCount: 1, artist: "Artist One", listenCount: 2 },
      { albumCount: 1, artist: "Artist Two", listenCount: 1 },
    ]);
  });

  it("returns prior-period summaries for fixed ranges", () => {
    const albums = {
      current: album({
        key: "current - album",
        artist: "Current",
        listens: [localDate(5, 18), localDate(5, 19)],
      }),
      prior: album({
        key: "prior - album",
        artist: "Prior",
        listens: [localDate(5, 8), localDate(5, 10)],
      }),
    };

    const result = aggregateDiscoveryInsights(albums, "7d", { now: NOW });

    expect(result.summary).toEqual({
      newToYou: 2,
      catalog: 0,
      totalListens: 2,
    });
    expect(result.previousPeriod.summary).toEqual({
      newToYou: 2,
      catalog: 0,
      totalListens: 2,
    });
    expect(result.previousPeriod.concentration.overallShare).toBe(100);
  });

  it("exposes new-to-you and catalog trend series", () => {
    const albums = {
      one: album({
        key: "artist - album",
        artist: "Artist",
        listens: [localDate(5, 18), localDate(5, 18, 13)],
      }),
    };

    const weekly = aggregateDiscoveryInsights(albums, "7d", { now: NOW });
    const populated = weekly.trendSeries.find((point) => point.total === 2);
    expect(populated).toMatchObject({
      newToYou: 2,
      catalog: 0,
      total: 2,
    });
  });

  it("keeps repeats new to you across buckets when the album was discovered in the selected year", () => {
    const result = aggregateDiscoveryInsights(
      {
        one: album({
          key: "artist - album",
          artist: "Artist",
          listens: ["2025-09-25T12:00:00.000Z", localDate(5, 18)],
        }),
      },
      "1y",
      { now: NOW }
    );

    expect(result.summary).toEqual({
      newToYou: 2,
      catalog: 0,
      totalListens: 2,
    });
    expect(result.buckets.filter((bucket) => bucket.total > 0)).toHaveLength(2);
  });

  it("treats the first listen exactly at the window boundary as new to you", () => {
    const result = aggregateDiscoveryInsights(
      {
        one: album({
          key: "artist - album",
          artist: "Artist",
          listens: [localDate(5, 14, 0), localDate(5, 20)],
        }),
      },
      "7d",
      { now: NOW }
    );

    expect(result.summary).toEqual({
      newToYou: 2,
      catalog: 0,
      totalListens: 2,
    });
  });
});
