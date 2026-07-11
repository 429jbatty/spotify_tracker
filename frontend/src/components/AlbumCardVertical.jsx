import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

import AlbumArtwork from "./AlbumArtwork";
import AlbumRatingBadge from "./AlbumRatingBadge";
import AlbumHeader from "./AlbumCardHeader";
import AlbumListenHistory from "./AlbumListenHistory";
import AlbumMetadata from "./AlbumMetadata";

import { getListenStats } from "./utils/albumHelpers";
import { cn } from "@/lib/utils";

function formatListenDate(value) {
  if (!value) return null;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function AlbumCardVertical({
  album,
  className,
  discoveryLabel = "New discovery",
  discoveredInRange = false,
  highlightDiscovery = false,
  latestInRangeListen,
  onClick,
  rangeListenCount = 0,
}) {

  const listenStats = getListenStats(album.listen_history);
  const latestInRangeLabel = formatListenDate(latestInRangeListen);
  const showRangeListenCount = rangeListenCount > 1;
  const clickableProps = onClick
    ? {
        role: "button",
        tabIndex: 0,
        onClick,
        onKeyDown: (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onClick();
          }
        },
      }
    : {};

  return (
    <Card
      className={cn(
        "group relative overflow-visible transition-all duration-300 hover:shadow-lg border border-border bg-card",
        highlightDiscovery && "border-chart-3/50 ring-2 ring-chart-3/45",
        onClick && "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className
      )}
      {...clickableProps}
    >
      {discoveredInRange ? (
        <div className="absolute left-3 top-0 z-20 -translate-y-1/2">
          <Badge
            className={cn(
              "bg-background shadow-sm",
              highlightDiscovery
                ? "border-chart-3/40 text-chart-3"
                : "border-border text-muted-foreground"
            )}
            variant="outline"
          >
            {discoveryLabel}
          </Badge>
        </div>
      ) : null}

      {album.rating ? (
        <div className="absolute right-3 top-0 z-20 -translate-y-1/2">
          <AlbumRatingBadge rating={album.rating} compact />
        </div>
      ) : null}

      <CardHeader className="p-0 bg-card">
        <AlbumArtwork album={album} />

        <AlbumHeader
          album={album}
          listenStats={listenStats}
        />

      </CardHeader>

      <CardContent className="space-y-4 p-6">
        {latestInRangeLabel || showRangeListenCount ? (
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            {latestInRangeLabel ? (
              <span>Latest in range: {latestInRangeLabel}</span>
            ) : (
              <span />
            )}
            {showRangeListenCount ? (
              <Badge className="shrink-0" variant="secondary">
                {rangeListenCount} listens in range
              </Badge>
            ) : null}
          </div>
        ) : null}

        <AlbumListenHistory listenStats={listenStats} />

        <AlbumMetadata album={album} />

      </CardContent>

    </Card>
  );
}

export default AlbumCardVertical;
