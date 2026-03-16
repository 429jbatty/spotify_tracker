import React, { useMemo, useState } from "react";
import AlbumCard from "./AlbumCard";
import StatsBar from "./StatsBar";
import DiscoveryLineChart from "./DiscoveryChart";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";

const TIME_RANGES = {
  "7d": 7,
  "30d": 30,
  "1y": 365,
  all: Infinity,
};

export default function Discovery({ albums }) {
  const [timeRange, setTimeRange] = useState("all");

  // Convert albums object to array
  const albumsArray = useMemo(() => Object.values(albums), [albums]);

  // Filter albums by selected time range
  const filteredAlbums = useMemo(() => {
    if (timeRange === "all") return albumsArray;

    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - TIME_RANGES[timeRange]);

    return albumsArray.filter((album) =>
      album.listen_history?.some(
        (dateStr) => new Date(dateStr) >= cutoff
      )
    );
  }, [albumsArray, timeRange]);

  // Recent discoveries (sorted by first listen in filtered set)
  const recentDiscoveries = useMemo(() => {
    return filteredAlbums
      .map((album) => ({
        ...album,
        firstListenDate: album.listen_history?.[0] || null,
        isNewArtist:
          albumsArray.filter((a) => a.artist === album.artist).length === 1,
      }))
      .sort(
        (a, b) =>
          new Date(b.firstListenDate).getTime() -
          new Date(a.firstListenDate).getTime()
      );
  }, [filteredAlbums, albumsArray]);

  // Split artists into new vs returning
  const { newArtistsList, returningArtistsList } = useMemo(() => {
    const seenArtists = new Set();
    const newArtists = [];
    const returningArtists = [];

    filteredAlbums.forEach((album) => {
      const artistEntry = {
        name: album.artist,
        albums: [album],
        firstListenDate: album.listen_history?.[0] || "",
      };
      if (!seenArtists.has(album.artist)) {
        seenArtists.add(album.artist);
        newArtists.push(artistEntry);
      } else {
        const existing = returningArtists.find((a) => a.name === album.artist);
        if (existing) {
          existing.albums.push(album);
        } else {
          returningArtists.push(artistEntry);
        }
      }
    });

    return { newArtistsList: newArtists, returningArtistsList: returningArtists };
  }, [filteredAlbums]);

  return (
    <div className="p-6 space-y-6">

      {/* --- Time Range Toggle --- */}
      <div className="flex">
        <Tabs value={timeRange} onValueChange={setTimeRange}>
          <TabsList className="bg-background/20 backdrop-blur-sm rounded-lg p-1">
            {Object.keys(TIME_RANGES).map((rangeKey) => (
              <TabsTrigger
                key={rangeKey}
                value={rangeKey}
                className="px-3 py-1 text-sm font-medium rounded-md transition-all
                  text-muted-foreground
                  data-[state=active]:bg-background/70
                  data-[state=active]:text-primary
                  hover:text-primary"
              >
                {rangeKey === "7d"
                  ? "7D"
                  : rangeKey === "30d"
                  ? "30D"
                  : rangeKey === "1y"
                  ? "1Y"
                  : "All"}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      
      <StatsBar albums={filteredAlbums} />
      <DiscoveryLineChart albums={filteredAlbums} timeRange={timeRange} />

      {/* --- Recent Discovery Feed --- */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Recent Discoveries</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {recentDiscoveries.map((album) => (
            <AlbumCard
              key={album.release_group_mbid}
              album={album}
              showNewArtistBadge={album.isNewArtist}
              showFirstListenDate
              expandableTracks
              className="hover:scale-105 transition-transform"
            />
          ))}
        </div>
      </section>
    </div>
  );
}