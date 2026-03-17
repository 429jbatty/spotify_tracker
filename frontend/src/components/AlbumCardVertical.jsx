import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";

import AlbumArtwork from "./AlbumArtwork";
import AlbumHeader from "./AlbumCardHeader";
import AlbumListenHistory from "./AlbumListenHistory";
import AlbumMetadata from "./AlbumMetadata";
import AlbumCredits from "./AlbumCredits";
import TracklistModal from "./TracklistModal";

import {
  groupAlbumCredits,
  getListenStats,
} from "./utils/albumHelpers";

function AlbumCardVertical({ album }) {

  const groupedCredits = groupAlbumCredits(album);
  const listenStats = getListenStats(album.listen_history);

  return (
    <Card className="group overflow-hidden transition-all duration-300 hover:shadow-lg border border-border bg-card">

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

        <AlbumCredits groupedCredits={groupedCredits} />

        {album.tracklist?.length > 0 && (
          <div className="border-t border-border pt-4">
            <TracklistModal album={album} />
          </div>
        )}

      </CardContent>

    </Card>
  );
}

export default AlbumCardVertical;