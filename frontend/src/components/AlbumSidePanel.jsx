import AlbumArtwork from "./AlbumArtwork";
import AlbumHeader from "./AlbumCardHeader";
import ListenCountBadge from "./ListenCountBadge";
import AlbumRatingBadge from "./AlbumRatingBadge";
import AlbumListenHistory from "./AlbumListenHistory";
import AlbumListenEditor from "./dataQuality/AlbumListenEditor";
import AlbumMetadata from "./AlbumMetadata";
import AlbumMetadataActions from "./AlbumMetadataActions";
import AlbumTrackDetails from "./AlbumTrackDetails";
import AlbumUserFeedback from "./AlbumUserFeedback";
import AlbumUserTags from "./AlbumUserTags";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
    <div className="relative flex flex-col gap-6 p-6">

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
      <section className="border-t pt-4">
        <Accordion type="single" collapsible className="w-full">
          <AccordionItem value="listen-history" className="border-0">
            <AccordionTrigger className="hover:no-underline py-2 px-0">
              <div className="flex w-full items-center justify-between gap-4 pr-2 text-left">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    Listen history
                  </h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {listenStats?.count
                      ? `${listenStats.count} listen${listenStats.count === 1 ? "" : "s"} logged`
                      : "No listens logged"}
                  </p>
                </div>
              </div>
            </AccordionTrigger>

            <AccordionContent className="pb-0">
              {showListenGraph && <Sparkline counts={sparklineCounts} />}
              {showListenHistory && <AlbumListenHistory listenStats={listenStats} />}
              <div className="mt-4">
                <AlbumListenEditor
                  album={displayAlbum}
                  onAlbumUpdated={handleAlbumUpdated}
                  onDataChanged={onDataChanged}
                />
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </section>

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

      {/* Tracks and credits */}
      {hasTrackDetails && (
        <section className="border-t pt-4">
          <div className="hidden lg:block">
            <AlbumTrackDetails
              album={displayAlbum}
              open={trackDetailsOpen}
              onOpenChange={onTrackDetailsOpenChange}
              variant="trigger"
            />
          </div>
          <div className="lg:hidden">
            <AlbumTrackDetails
              album={displayAlbum}
              onFilterSelect={onFilterSelect}
              open={trackDetailsOpen}
              onOpenChange={onTrackDetailsOpenChange}
            />
          </div>
        </section>
      )}

    </div>
  );
}

export default AlbumSidePanel;
