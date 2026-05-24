import AlbumArtwork from "./AlbumArtwork";
import AlbumHeader from "./AlbumCardHeader";
import ListenCountBadge from "./ListenCountBadge";
import AlbumRatingBadge from "./AlbumRatingBadge";
import AlbumListenHistory from "./AlbumListenHistory";
import AlbumMetadata from "./AlbumMetadata";
import AlbumMetadataActions from "./AlbumMetadataActions";
import AlbumTrackDetails from "./AlbumTrackDetails";
import AlbumUserFeedback from "./AlbumUserFeedback";
import AlbumUserTags from "./AlbumUserTags";
import { normalizeAlbum } from "../services/albumNormalizer";
import { buildSparkline } from "./utils/albumHelpers";

import { getListenStats } from "./utils/albumHelpers";

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

function AlbumSidePanel({
  album,
  onFilterSelect,
  onAlbumUpdated,
  onAlbumDeleted,
  onDataChanged,
  trackDetailsOpen = false,
  onTrackDetailsOpenChange,
}) {
  const displayAlbum = normalizeAlbum(album);

  const handleAlbumUpdated = (updatedAlbum) => {
    const normalizedAlbum = normalizeAlbum(updatedAlbum);
    onAlbumUpdated?.(normalizedAlbum);
  };

  const listenStats = getListenStats(displayAlbum.listen_history);
  const sparklineCounts = buildSparkline(displayAlbum.listen_history, 12);
  const showListenGraph =
    (displayAlbum.listen_history?.length || 0) >= 3 &&
    sparklineCounts.some((count) => count > 0);
  const showListenHistory = listenStats && listenStats.count > 0;
  const hasTrackDetails = displayAlbum.tracklist?.length > 0;

  return (
    <div
      className={`relative grid gap-6 p-6 ${
        trackDetailsOpen && hasTrackDetails
          ? "lg:grid-cols-[minmax(18rem,24rem)_minmax(30rem,1fr)]"
          : ""
      }`}
    >
      <div className="flex flex-col gap-6">

      {listenStats && listenStats.count > 0 ? (
        <div className="absolute right-6 top-6 z-10">
          <ListenCountBadge count={listenStats.count} />
        </div>
      ) : null}

      {displayAlbum.rating ? (
        <div className="flex justify-center">
          <AlbumRatingBadge rating={displayAlbum.rating} />
        </div>
      ) : null}

      {/* Artwork */}
      <div className="flex justify-center">
        <div className="w-56 h-56">
          <AlbumArtwork album={displayAlbum} />
        </div>
      </div>

      {/* Title / Artist */}
      <div className="text-center">
        <AlbumHeader album={displayAlbum} /> {/* header no longer contains stats */}
      </div>

      {/* Listen history */}
      {showListenHistory && (
        <section className="border-t pt-4">
          <h3 className="text-sm font-semibold text-foreground">
            Listen history
          </h3>
          {showListenGraph && <Sparkline counts={sparklineCounts} />}
          <AlbumListenHistory listenStats={listenStats} />
        </section>
      )}

      {/* Metadata */}
      <section className="border-t pt-4">
        <h3 className="mb-3 text-sm font-semibold text-foreground">
          Album metadata
        </h3>
        <AlbumMetadata album={displayAlbum} onFilterSelect={onFilterSelect} />
      </section>

      <AlbumUserFeedback
        album={displayAlbum}
        onAlbumUpdated={handleAlbumUpdated}
        onDataChanged={onDataChanged}
      />

      <AlbumUserTags
        album={displayAlbum}
        onAlbumUpdated={handleAlbumUpdated}
        onDataChanged={onDataChanged}
        onFilterSelect={onFilterSelect}
      />

      <AlbumMetadataActions
        album={displayAlbum}
        onAlbumUpdated={handleAlbumUpdated}
        onAlbumDeleted={onAlbumDeleted}
        onDataChanged={onDataChanged}
      />
      </div>

      {/* Tracks and credits */}
      {hasTrackDetails && (
        <section
          className={`border-t pt-4 ${
            trackDetailsOpen ? "lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0" : ""
          }`}
        >
          <AlbumTrackDetails
            album={displayAlbum}
            onFilterSelect={onFilterSelect}
            open={trackDetailsOpen}
            onOpenChange={onTrackDetailsOpenChange}
          />
        </section>
      )}

    </div>
  );
}

export default AlbumSidePanel;
