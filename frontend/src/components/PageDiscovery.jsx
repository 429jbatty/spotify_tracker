import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import AlbumCardVertical from "./AlbumCardVertical";
import AlbumPanelSheet from "./AlbumPanelSheet";
import DiscoveryMetricRail from "./discovery/DiscoveryMetricRail";
import DiscoveryQualityCard from "./discovery/DiscoveryQualityCard";
import NewToYouTrend from "./discovery/NewToYouTrend";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import { buildDiscoveryFeed } from "./utils/discoveryFeed";
import { aggregateDiscoveryInsights } from "./utils/discoveryInsights";
import { normalizeDiscoveryRange } from "@/routing";
import EmptyLibraryState from "@/components/onboarding/EmptyLibraryState";

const TIME_RANGES = {
  "7d": 7,
  "30d": 30,
  "1y": 365,
};

const TIME_RANGE_LABELS = {
  "7d": "7D",
  "30d": "30D",
  "1y": "1Y",
};

function getNewToYouListeningShare(summary) {
  return summary.totalListens === 0
    ? 0
    : (summary.newToYou / summary.totalListens) * 100;
}

function getCatalogListeningShare(summary) {
  return summary.totalListens === 0
    ? 0
    : (summary.catalog / summary.totalListens) * 100;
}

function getDelta(current, previous, kind) {
  if (current == null || previous == null) return null;
  return { kind, value: current - previous };
}

function getComparisonLabel(timeRange) {
  if (timeRange === "7d") return "previous 7 days";
  if (timeRange === "30d") return "previous 30 days";
  return "previous 365 days";
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
  onOpenAlbum,
  onAddAlbum,
  onImport,
  onConnectSpotify,
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const timeRange = normalizeDiscoveryRange(
    searchParams.get("range"),
    Object.keys(TIME_RANGES)
  );
  const [selectedAlbum, setSelectedAlbum] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const analysisNow = useMemo(() => new Date(), []);
  const allAlbumsArray = useMemo(() => Object.values(allAlbums), [allAlbums]);
  const listenRecords = useMemo(
    () => buildDiscoveryListenRecords(allAlbumsArray),
    [allAlbumsArray]
  );
  const discoveryInsights = useMemo(
    () => aggregateDiscoveryInsights(allAlbums, timeRange, { now: analysisNow }),
    [allAlbums, analysisNow, timeRange]
  );
  const recentListens = useMemo(
    () => buildDiscoveryFeed(allAlbumsArray, timeRange, { now: analysisNow }),
    [allAlbumsArray, analysisNow, timeRange]
  );
  const newToYouListeningShare = getNewToYouListeningShare(discoveryInsights.summary);
  const previousNewToYouListeningShare = discoveryInsights.previousPeriod
    ? getNewToYouListeningShare(discoveryInsights.previousPeriod.summary)
    : null;
  const catalogListeningShare = getCatalogListeningShare(discoveryInsights.summary);
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
      delta: getDelta(newToYouListeningShare, previousNewToYouListeningShare, "points"),
      newToYouListeningShare,
      label: "New-to-you listening",
      catalogListeningShare,
      tooltip:
        "The share of listens in this range to albums you first heard during this same range. The rest is catalog listening.",
      type: "mix",
      value: `${newToYouListeningShare.toFixed(0)}% new`,
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
    if (onOpenAlbum) {
      onOpenAlbum(album);
      return;
    }
    setSelectedAlbum(album);
    setPanelOpen(true);
  };

  const handleRangeChange = (nextRange) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("range", nextRange);
      return next;
    });
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
      <div className="space-y-7 py-6">
        {allAlbumsArray.length === 0 && onAddAlbum && (
          <EmptyLibraryState
            view="discovery"
            onAddAlbum={onAddAlbum}
            onImport={onImport}
            onConnectSpotify={onConnectSpotify}
          />
        )}
        {allAlbumsArray.length > 0 && <div className="px-6">
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

            <Tabs value={timeRange} onValueChange={handleRangeChange}>
              <TabsList aria-label="Discovery activity range">
                {Object.keys(TIME_RANGES).map((rangeKey) => (
                  <TabsTrigger key={rangeKey} value={rangeKey}>
                    {TIME_RANGE_LABELS[rangeKey]}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>

          <DiscoveryMetricRail metrics={metricRail} />
        </section>
        </div>}

        {allAlbumsArray.length > 0 && <>
        <div className="px-6"><NewToYouTrend series={discoveryInsights.trendSeries} /></div>

        <div className="px-6"><DiscoveryQualityCard listens={listenRecords} selectedRange={timeRange} /></div>

        <section className="space-y-4 px-6">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">
              Listens in this range
            </h2>
          </div>

          {recentListens.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              No album listens in this range.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
              {recentListens.map((album) => (
                <AlbumCardVertical
                  key={album.id || album.release_group_mbid}
                  album={album}
                  className="transition-shadow hover:shadow-md"
                  expandableTracks
                  discoveredInRange={album.discoveredInRange}
                  discoveryLabel={album.discoveryLabel}
                  highlightDiscovery={album.highlightDiscovery}
                  latestInRangeListen={album.latestInRangeListen}
                  onClick={() => handleAlbumClick(album)}
                  rangeListenCount={album.inRangeListenCount}
                />
              ))}
            </div>
          )}
        </section>
        </>}
      </div>

      {!onOpenAlbum && (
        <AlbumPanelSheet
          album={selectedAlbum}
          onAlbumDeleted={handleAlbumDeleted}
          onAlbumUpdated={updateSelectedAlbum}
          onDataChanged={onDataChanged}
          onFilterSelect={onFilterSelect}
          onOpenChange={setPanelOpen}
          open={panelOpen}
        />
      )}
    </>
  );
}
