import { useMemo, useState } from "react";
import { ArrowRight } from "lucide-react";
import AlbumCardVertical from "./AlbumCardVertical";
import AlbumPanelSheet from "./AlbumPanelSheet";
import DiscoveryMetricRail from "./discovery/DiscoveryMetricRail";
import DiscoveryQualityCard from "./discovery/DiscoveryQualityCard";
import NewVsReplayTrend from "./discovery/NewVsReplayTrend";
import { Button } from "./ui/button";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import { aggregateDiscoveryInsights } from "./utils/discoveryInsights";

const TIME_RANGES = {
  "7d": 7,
  "30d": 30,
  "1y": 365,
  all: Infinity,
};

function getFirstListen(album) {
  return (album.listen_history || [])
    .map((dateValue) => new Date(dateValue))
    .filter((date) => !Number.isNaN(date.getTime()))
    .sort((left, right) => left.getTime() - right.getTime())[0] || null;
}

function getRangeStart(timeRange, now) {
  if (timeRange === "all") return new Date(0);

  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - (TIME_RANGES[timeRange] - 1));
  return start;
}

function getDiscoveryRate(summary) {
  return summary.totalListens === 0
    ? 0
    : (summary.newAlbums / summary.totalListens) * 100;
}

function getReplayRate(summary) {
  return summary.totalListens === 0
    ? 0
    : (summary.relistens / summary.totalListens) * 100;
}

function getDelta(current, previous, kind) {
  if (current == null || previous == null) return null;
  return { kind, value: current - previous };
}

function getComparisonLabel(timeRange) {
  if (timeRange === "7d") return "previous 7 days";
  if (timeRange === "30d") return "previous 30 days";
  if (timeRange === "1y") return "previous 365 days";
  return null;
}

function getRecentDiscoveries(albums, allAlbums, timeRange, now) {
  const rangeStart = getRangeStart(timeRange, now);
  const artistFirstListen = new Map();

  allAlbums.forEach((album) => {
    const firstListen = getFirstListen(album);
    if (!firstListen) return;

    const artistKey = String(album.artist || "").trim().toLocaleLowerCase();
    const currentFirst = artistFirstListen.get(artistKey);
    if (!currentFirst || firstListen.getTime() < currentFirst.getTime()) {
      artistFirstListen.set(artistKey, firstListen);
    }
  });

  return albums
    .map((album) => {
      const firstListen = getFirstListen(album);
      const artistKey = String(album.artist || "").trim().toLocaleLowerCase();
      return {
        ...album,
        firstListenDate: firstListen?.toISOString() || null,
        firstListenTime: firstListen?.getTime() || null,
        isNewArtist:
          firstListen != null &&
          firstListen.getTime() === artistFirstListen.get(artistKey)?.getTime(),
      };
    })
    .filter(
      (album) =>
        album.firstListenTime != null &&
        album.firstListenTime >= rangeStart.getTime() &&
        album.firstListenTime <= now.getTime()
    )
    .sort((left, right) => right.firstListenTime - left.firstListenTime);
}

function buildDiscoveryListenRecords(albums) {
  return albums.flatMap((album) =>
    (album.listen_history || []).map((listenDate) => ({
      album,
      listenDate,
    }))
  );
}

export default function Discovery({
  albums,
  allAlbums = albums,
  onFilterSelect,
  onDataChanged,
}) {
  const [timeRange, setTimeRange] = useState("1y");
  const [showAllDiscoveries, setShowAllDiscoveries] = useState(false);
  const [selectedAlbum, setSelectedAlbum] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const analysisNow = useMemo(() => new Date(), []);
  const albumsArray = useMemo(() => Object.values(albums), [albums]);
  const allAlbumsArray = useMemo(() => Object.values(allAlbums), [allAlbums]);
  const listenRecords = useMemo(
    () => buildDiscoveryListenRecords(allAlbumsArray),
    [allAlbumsArray]
  );
  const discoveryInsights = useMemo(
    () => aggregateDiscoveryInsights(allAlbums, timeRange, { now: analysisNow }),
    [allAlbums, analysisNow, timeRange]
  );
  const recentDiscoveries = useMemo(
    () => getRecentDiscoveries(albumsArray, allAlbumsArray, timeRange, analysisNow),
    [albumsArray, allAlbumsArray, analysisNow, timeRange]
  );
  const visibleDiscoveries = showAllDiscoveries
    ? recentDiscoveries
    : recentDiscoveries.slice(0, 8);
  const discoveryRate = getDiscoveryRate(discoveryInsights.summary);
  const previousDiscoveryRate = discoveryInsights.previousPeriod
    ? getDiscoveryRate(discoveryInsights.previousPeriod.summary)
    : null;
  const replayRate = getReplayRate(discoveryInsights.summary);
  const comparisonLabel = getComparisonLabel(timeRange);
  const metricRail = [
    {
      comparisonLabel,
      delta: getDelta(
        discoveryInsights.summary.totalListens,
        discoveryInsights.previousPeriod?.summary.totalListens,
        "count"
      ),
      label: "Total listens",
      tooltip:
        "Total completed album listens in the selected range. The comparison uses the immediately preceding range of the same length.",
      value: discoveryInsights.summary.totalListens.toLocaleString(),
    },
    {
      comparisonLabel,
      delta: getDelta(discoveryRate, previousDiscoveryRate, "points"),
      discoveryRate,
      label: "Discovery mix",
      replayRate,
      tooltip:
        "First-time album listens versus relistens in the selected range. These two percentages are the two sides of the same listen mix.",
      type: "mix",
      value: `${discoveryRate.toFixed(0)}% new`,
    },
    {
      comparisonLabel,
      delta: getDelta(
        discoveryInsights.concentration.overallShare,
        discoveryInsights.previousPeriod?.concentration.overallShare,
        "points"
      ),
      label: "Artist concentration",
      tooltip:
        "The share of listens in the selected range that came from your five most-played artists. Higher means listening was clustered around fewer artists.",
      value: `${discoveryInsights.concentration.overallShare.toFixed(0)}%`,
    },
  ];

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
      <div className="space-y-7 p-6">
        <section className="space-y-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-foreground">
                Discovery
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">
                How new music enters your rotation and what stays.
              </p>
            </div>

            <Tabs value={timeRange} onValueChange={setTimeRange}>
              <TabsList aria-label="Discovery activity range">
                {Object.keys(TIME_RANGES).map((rangeKey) => (
                  <TabsTrigger key={rangeKey} value={rangeKey}>
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

          <DiscoveryMetricRail metrics={metricRail} />
        </section>

        <NewVsReplayTrend series={discoveryInsights.trendSeries} />

        <DiscoveryQualityCard listens={listenRecords} selectedRange={timeRange} />

        <section className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">
              Recent discoveries
            </h2>
            {recentDiscoveries.length > 8 ? (
              <Button
                className="text-primary"
                onClick={() => setShowAllDiscoveries((current) => !current)}
                variant="ghost"
              >
                {showAllDiscoveries ? "Show fewer" : "View all discoveries"}
                <ArrowRight />
              </Button>
            ) : null}
          </div>

          {visibleDiscoveries.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              No first-time album listens in this range.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
              {visibleDiscoveries.map((album) => (
                <AlbumCardVertical
                  key={album.id || album.release_group_mbid}
                  album={album}
                  className="transition-shadow hover:shadow-md"
                  expandableTracks
                  onClick={() => handleAlbumClick(album)}
                  showFirstListenDate
                  showNewArtistBadge={album.isNewArtist}
                />
              ))}
            </div>
          )}
        </section>
      </div>

      <AlbumPanelSheet
        album={selectedAlbum}
        onAlbumDeleted={handleAlbumDeleted}
        onAlbumUpdated={updateSelectedAlbum}
        onDataChanged={onDataChanged}
        onFilterSelect={onFilterSelect}
        onOpenChange={setPanelOpen}
        open={panelOpen}
      />
    </>
  );
}
