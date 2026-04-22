import { useEffect, useState } from "react";
import AlbumArtwork from "./AlbumArtwork";
import AlbumHeader from "./AlbumCardHeader";
import ListenCountBadge from "./ListenCountBadge";
import AlbumListenHistory from "./AlbumListenHistory";
import AlbumMetadata from "./AlbumMetadata";
import AlbumMetadataActions from "./AlbumMetadataActions";
import AlbumTrackDetails from "./AlbumTrackDetails";
import AlbumUserTags from "./AlbumUserTags";
import { normalizeAlbum } from "../services/albumNormalizer";
import { buildSparkline } from "./utils/albumHelpers";

import {
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

function AlbumSidePanel({
  album,
  onFilterSelect,
  onAlbumUpdated,
  onAlbumDeleted,
  onDataChanged,
}) {
  const [displayAlbum, setDisplayAlbum] = useState(() => normalizeAlbum(album));

  useEffect(() => {
    setDisplayAlbum(normalizeAlbum(album));
  }, [album]);

  const handleAlbumUpdated = (updatedAlbum) => {
    const normalizedAlbum = normalizeAlbum(updatedAlbum);
    setDisplayAlbum(normalizedAlbum);
    onAlbumUpdated?.(normalizedAlbum);
  };

  const listenStats = getListenStats(displayAlbum.listen_history);
  const sparklineCounts = buildSparkline(displayAlbum.listen_history, 12);
  const showListenGraph =
    (displayAlbum.listen_history?.length || 0) >= 3 &&
    sparklineCounts.some((count) => count > 0);

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
          <AlbumArtwork album={displayAlbum} />
        </div>
      </div>

      {/* Title / Artist */}
      <div className="text-center">
        <AlbumHeader album={displayAlbum} /> {/* header no longer contains stats */}
      </div>

      {/* Sparkline (only renders if data exists) */}
      {showListenGraph && (
        <section className="border-t pt-4">
          <h3 className="text-sm font-medium text-muted-foreground mb-2">
            Listen History
          </h3>
          <Sparkline counts={sparklineCounts} />
        </section>
      )}

      {/* Album Listen History (raw details) */}
      {showListenGraph && listenStats && (
        <section className="border-t pt-4">
          <AlbumListenHistory listenStats={listenStats} />
        </section>
      )}

      {/* Metadata */}
      <section className="border-t pt-4">
        <AlbumMetadata album={displayAlbum} onFilterSelect={onFilterSelect} />
      </section>

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

      {/* Tracks and credits */}
      {displayAlbum.tracklist?.length > 0 && (
        <section className="border-t pt-4">
          <AlbumTrackDetails album={displayAlbum} onFilterSelect={onFilterSelect} />
        </section>
      )}

    </div>
  );
}

export default AlbumSidePanel;
