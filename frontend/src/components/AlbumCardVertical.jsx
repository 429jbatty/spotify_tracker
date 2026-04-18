import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";

import AlbumArtwork from "./AlbumArtwork";
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
        "group overflow-hidden transition-all duration-300 hover:shadow-lg border border-border bg-card",
        onClick && "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className
      )}
      {...clickableProps}
    >

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
