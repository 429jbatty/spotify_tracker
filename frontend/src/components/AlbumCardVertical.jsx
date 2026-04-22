import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";

import AlbumArtwork from "./AlbumArtwork";
import AlbumRatingBadge from "./AlbumRatingBadge";
import AlbumHeader from "./AlbumCardHeader";
import AlbumListenHistory from "./AlbumListenHistory";
import AlbumMetadata from "./AlbumMetadata";

import { getListenStats } from "./utils/albumHelpers";
import { cn } from "@/lib/utils";

function AlbumCardVertical({ album, onClick, className }) {

  const listenStats = getListenStats(album.listen_history);
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
        onClick && "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className
      )}
      {...clickableProps}
    >
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

        <AlbumListenHistory listenStats={listenStats} />

        <AlbumMetadata album={album} />

      </CardContent>

    </Card>
  );
}

export default AlbumCardVertical;
