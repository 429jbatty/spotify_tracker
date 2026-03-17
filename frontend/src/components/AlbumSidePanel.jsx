import AlbumArtwork from "./AlbumArtwork";
import AlbumHeader from "./AlbumCardHeader";
import ListenCountBadge from "./ListenCountBadge";
import AlbumListenHistory from "./AlbumListenHistory";
import AlbumMetadata from "./AlbumMetadata";
import AlbumCredits from "./AlbumCredits";
import TracklistModal from "./TracklistModal";
import { buildSparkline } from "./utils/albumHelpers";

import {
  groupAlbumCredits,
  getListenStats,
} from "./utils/albumHelpers";

// --- Sparkline Component ---
function Sparkline({ counts = [], barWidth = 4, maxHeight = 40 }) {
  if (!counts || counts.length === 0) return null; // render nothing if empty

  const max = Math.max(...counts, 1); // prevent division by 0

  return (
    <div className="flex items-end gap-1 h-[40px] mt-2">
      {counts.map((count, i) => {
        const height = (count / max) * maxHeight;
        return (
          <div
            key={i}
            className="bg-foreground rounded-sm"
            style={{ width: `${barWidth}px`, height: `${height}px` }}
          />
        );
      })}
    </div>
  );
}

function AlbumSidePanel({ album }) {
  const groupedCredits = groupAlbumCredits(album);
  const listenStats = getListenStats(album.listen_history);
  const sparklineCounts = buildSparkline(album.listen_history, 12);

  return (
    <div className="relative flex flex-col gap-6 p-6 overflow-y-auto">

      {/* Top-right listen count badge */}
      {listenStats && listenStats.count > 0 && (
        <div className="absolute top-6 right-6 z-10">
          <ListenCountBadge count={listenStats.count} />
        </div>
      )}

      {/* Artwork */}
      <div className="flex justify-center">
        <div className="w-56 h-56">
          <AlbumArtwork album={album} />
        </div>
      </div>

      {/* Title / Artist */}
      <div className="text-center">
        <AlbumHeader album={album} /> {/* header no longer contains stats */}
      </div>

      {/* Sparkline (only renders if data exists) */}
      {sparklineCounts.length > 0 && (
        <section className="border-t pt-4">
          <h3 className="text-sm font-medium text-muted-foreground mb-2">
            Listen History
          </h3>
          <Sparkline counts={sparklineCounts} />
        </section>
      )}

      {/* Album Listen History (raw details) */}
      {listenStats && (
        <section className="border-t pt-4">
          <AlbumListenHistory listenStats={listenStats} />
        </section>
      )}

      {/* Metadata */}
      <section className="border-t pt-4">
        <AlbumMetadata album={album} />
      </section>

      {/* Credits */}
      <section className="border-t pt-4">
        <AlbumCredits groupedCredits={groupedCredits} />
      </section>

      {/* Tracklist */}
      {album.tracklist?.length > 0 && (
        <section className="border-t pt-4">
          <TracklistModal album={album} />
        </section>
      )}

    </div>
  );
}

export default AlbumSidePanel;