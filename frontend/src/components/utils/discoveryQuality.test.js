import { describe, expect, it } from "vitest";
import { buildDiscoveryQuality } from "./discoveryQuality";

const NOW = new Date(2026, 5, 20, 18, 0, 0);

function date(monthIndex, day, hour = 12) {
  return new Date(2026, monthIndex, day, hour, 0, 0).toISOString();
}

function listen(listenDate, album) {
  return { album, listenDate };
}

describe("buildDiscoveryQuality", () => {
  it("buckets first-time discoveries by exact rating in the selected range", () => {
    const result = buildDiscoveryQuality(
      [
        listen(date(5, 18), { album_key: "great", rating: 9 }),
        listen(date(5, 18), { album_key: "good", rating: 7 }),
        listen(date(5, 18), { album_key: "low", rating: 4 }),
        listen(date(5, 18), { album_key: "unrated" }),
      ],
      "7d",
      { now: NOW }
    );

    expect(result.totalDiscoveries).toBe(4);
    expect(result.ratedDiscoveries).toBe(3);
    expect(result.unratedDiscoveries).toBe(1);
    expect(result.averageScore).toBeCloseTo(6.67);
    expect(result.percentGreat).toBeCloseTo(33.33);
    expect(
      result.buckets
        .filter((bucket) => bucket.count > 0)
        .map((bucket) => [bucket.score, bucket.count])
    ).toEqual([
      [9, 1],
      [7, 1],
      [4, 1],
    ]);
  });

  it("only counts an album when its first listen is in range", () => {
    const result = buildDiscoveryQuality(
      [
        listen(date(5, 1), { album_key: "old", rating: 10 }),
        listen(date(5, 18), { album_key: "old", rating: 10 }),
        listen(date(5, 18), { album_key: "new", rating: 8 }),
      ],
      "7d",
      { now: NOW }
    );

    expect(result.totalDiscoveries).toBe(1);
    expect(result.buckets.find((bucket) => bucket.score === 8).count).toBe(1);
  });

  it("uses score aliases and supports all-time discovery quality", () => {
    const result = buildDiscoveryQuality(
      [
        listen(date(0, 1), { album_key: "score", score: 8 }),
        listen(date(1, 1), { album_key: "user-score", user_score: 6 }),
        listen(date(2, 1), { album_key: "ranking", ranking: 5 }),
      ],
      "all",
      { now: NOW }
    );

    expect(result.totalDiscoveries).toBe(3);
    expect(result.ratedDiscoveries).toBe(3);
    expect(
      result.buckets
        .filter((bucket) => bucket.count > 0)
        .map((bucket) => [bucket.score, bucket.count])
    ).toEqual([
      [8, 1],
      [6, 1],
      [5, 1],
    ]);
  });

  it("returns an empty distribution when there are no discoveries", () => {
    const result = buildDiscoveryQuality(
      [listen(date(5, 1), { album_key: "old", rating: 8 })],
      "7d",
      { now: NOW }
    );

    expect(result.totalDiscoveries).toBe(0);
    expect(result.ratedDiscoveries).toBe(0);
    expect(result.averageScore).toBeNull();
    expect(result.percentGreat).toBeNull();
  });
});
