import { describe, expect, it } from "vitest";
import { normalizeAlbum } from "./albumNormalizer.jsx";

describe("normalizeAlbum", () => {
  it("keeps legacy tuple credits display-compatible", () => {
    const album = normalizeAlbum({
      release_year: 2026,
      tracklist: [
        {
          title: "Track",
          credits: [["Producer One", "producer", "co"]],
        },
      ],
    });

    expect(album.tracklist[0].credits).toEqual([["Producer One", "producer", "co"]]);
    expect(album.album_credits).toEqual([["Producer One", "producer", "co"]]);
  });

  it("normalizes enriched object credits into display tuples", () => {
    const album = normalizeAlbum({
      release_year: 2026,
      tracklist: [
        {
          title: "Track",
          credits: [
            {
              name: "Producer One",
              role: "producer",
              attributes: ["co", "additional"],
              artist_mbid: "artist-1",
              source_scope: "recording",
              ingestion_version: "musicbrainz_credit_v2",
            },
          ],
        },
      ],
    });

    expect(album.tracklist[0].credits).toEqual([
      ["Producer One", "producer", "co, additional"],
    ]);
    expect(album.album_credits).toEqual([
      ["Producer One", "producer", "co, additional"],
    ]);
  });
});
