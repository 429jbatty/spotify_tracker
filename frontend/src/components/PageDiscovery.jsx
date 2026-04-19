import { useMemo, useState } from "react";
import AlbumCardVertical from "./AlbumCardVertical";
import AlbumSidePanel from "./AlbumSidePanel";
import DiscoveryLineChart from "./DiscoveryChart";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import { Sheet, SheetContent } from "@/components/ui/sheet";

const TIME_RANGES = {
  "7d": 7,
  "30d": 30,
  "1y": 365,
  all: Infinity,
};

function SupportingMetric({ label, value }) {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold text-foreground">{value}</p>
    </div>
  );
}

function RotationList({ title, items }) {
  if (items.length === 0) return null;

  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.slice(0, 3).map(([label, count]) => (
          <span
            key={label}
            className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground"
          >
            {label} - {count}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function Discovery({
  albums,
  allAlbums = albums,
  onFilterSelect,
  onDataChanged,
}) {
  const [timeRange, setTimeRange] = useState("7d");
  const [selectedAlbum, setSelectedAlbum] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);

  // Convert albums object to array
  const albumsArray = useMemo(() => Object.values(albums), [albums]);
  const allAlbumsArray = useMemo(() => Object.values(allAlbums), [allAlbums]);

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
          allAlbumsArray.filter((a) => a.artist === album.artist).length === 1,
      }))
      .sort(
        (a, b) =>
          new Date(b.firstListenDate).getTime() -
          new Date(a.firstListenDate).getTime()
      );
  }, [filteredAlbums, allAlbumsArray]);

  const discoveryStats = useMemo(() => {
    const artistCounts = new Map();
    const labelCounts = new Map();
    const relistens = filteredAlbums.filter(
      (album) => (album.listen_history || []).length > 1
    );

    filteredAlbums.forEach((album) => {
      artistCounts.set(album.artist, (artistCounts.get(album.artist) || 0) + 1);
      if (album.label) {
        labelCounts.set(album.label, (labelCounts.get(album.label) || 0) + 1);
      }
    });

    const newArtists = filteredAlbums.filter(
      (album) =>
        allAlbumsArray.filter((item) => item.artist === album.artist).length === 1
    );
    const newLabels = filteredAlbums.filter(
      (album) =>
        album.label &&
        allAlbumsArray.filter((item) => item.label === album.label).length === 1
    );
    const topArtists = [...artistCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5);
    const topLabels = [...labelCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5);
    const totalArtists = new Set(filteredAlbums.map((album) => album.artist)).size;
    const avgAlbumsPerArtist =
      totalArtists === 0 ? "0.00" : (filteredAlbums.length / totalArtists).toFixed(2);

    return {
      totalAlbums: filteredAlbums.length,
      totalArtists,
      avgAlbumsPerArtist,
      newArtists: newArtists.length,
      newLabels: newLabels.length,
      relistens: relistens.length,
      topArtists,
      topLabels,
    };
  }, [filteredAlbums, allAlbumsArray]);

  const handleAlbumClick = (album) => {
    setSelectedAlbum(album);
    setPanelOpen(true);
  };

  const updateSelectedAlbum = (album) => {
    setSelectedAlbum((current) => (current ? { ...current, ...album } : album));
  };

  const handleAlbumDeleted = () => {
    setSelectedAlbum(null);
    setPanelOpen(false);
  };

  return (
    <>
      <div className="p-6 space-y-6">
        <section className="space-y-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-foreground">
                Discovery
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">
                New listens, returns, and patterns in the selected window.
              </p>
            </div>

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

          <div className="grid gap-4 lg:grid-cols-[1.15fr_2fr]">
            <div className="rounded-lg border border-border/70 bg-background/80 p-5 shadow-sm">
              <p className="text-xs font-medium text-muted-foreground">
                Albums in this window
              </p>
              <div className="mt-3 flex items-end gap-3">
                <span className="text-6xl font-semibold leading-none text-foreground">
                  {discoveryStats.totalAlbums}
                </span>
                <span className="pb-2 text-sm text-muted-foreground">
                  across {discoveryStats.totalArtists} artists
                </span>
              </div>
              <p className="mt-4 text-sm text-muted-foreground">
                {discoveryStats.avgAlbumsPerArtist} albums per artist
              </p>
            </div>

            <div className="rounded-lg border border-border/70 bg-background/80 p-5 shadow-sm">
              <div className="grid grid-cols-3 gap-4">
                <SupportingMetric
                  label="New artists"
                  value={discoveryStats.newArtists}
                />
                <SupportingMetric
                  label="New labels"
                  value={discoveryStats.newLabels}
                />
                <SupportingMetric label="Relistens" value={discoveryStats.relistens} />
              </div>

              <div className="mt-5 grid gap-4 border-t border-border pt-4 md:grid-cols-2">
                <RotationList
                  title="Artists in rotation"
                  items={discoveryStats.topArtists}
                />
                <RotationList
                  title="Labels in rotation"
                  items={discoveryStats.topLabels}
                />
              </div>
            </div>
          </div>
        </section>

      <DiscoveryLineChart albums={filteredAlbums} timeRange={timeRange} />

      {/* --- Recent Discovery Feed --- */}
      <section className="space-y-4">
        <h2 className="text-3xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-foreground via-foreground/50 to-foreground drop-shadow-md mb-6">
          Recent Discoveries
        </h2>        
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {recentDiscoveries.map((album) => (
            <AlbumCardVertical
              key={album.id || album.release_group_mbid}
              album={album}
              onClick={() => handleAlbumClick(album)}
              showNewArtistBadge={album.isNewArtist}
              showFirstListenDate
              expandableTracks
              className="hover:scale-105 transition-transform"
            />
          ))}
        </div>
      </section>
    </div>

      <Sheet open={panelOpen} onOpenChange={setPanelOpen}>
        <SheetContent
          side="right"
          className="w-[650px] sm:w-[750px] overflow-y-auto p-6"
        >
          {selectedAlbum && (
            <AlbumSidePanel
              album={selectedAlbum}
              onFilterSelect={onFilterSelect}
              onAlbumUpdated={updateSelectedAlbum}
              onAlbumDeleted={handleAlbumDeleted}
              onDataChanged={onDataChanged}
            />
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
