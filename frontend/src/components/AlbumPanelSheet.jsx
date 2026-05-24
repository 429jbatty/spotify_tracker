import { useState } from "react";
import AlbumSidePanel from "./AlbumSidePanel";
import AlbumTrackDetails from "./AlbumTrackDetails";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { normalizeAlbum } from "../services/albumNormalizer";

function AlbumPanelSheet({
  open,
  onOpenChange,
  album,
  searchTerm,
  onFilterSelect,
  onAlbumUpdated,
  onAlbumDeleted,
  onDataChanged,
}) {
  const [trackDetailsState, setTrackDetailsState] = useState({
    albumId: null,
    open: false,
  });
  const albumId = album?.id || null;
  const displayAlbum = album ? normalizeAlbum(album) : null;
  const hasTrackDetails = (displayAlbum?.tracklist?.length || 0) > 0;
  const hasCreditSearchMatches = (displayAlbum?.searchMatches || []).some(
    (match) => match.type === "credit"
  );
  const trackDetailsOpen = Boolean(
    open &&
      albumId &&
      (trackDetailsState.albumId === albumId
        ? trackDetailsState.open
        : hasCreditSearchMatches)
  );
  const setTrackDetailsOpen = (nextOpen) => {
    setTrackDetailsState({ albumId, open: nextOpen });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        aria-describedby={undefined}
        className={cn(
          "!w-[min(100vw,42rem)] !max-w-none overflow-visible p-0 sm:!w-[42rem] sm:!max-w-none"
        )}
      >
        <SheetTitle className="sr-only">
          {displayAlbum?.name ? `${displayAlbum.name} details` : "Album details"}
        </SheetTitle>
        {displayAlbum && (
          <>
            {trackDetailsOpen && hasTrackDetails ? (
              <aside className="absolute right-full top-0 hidden h-full w-[min(44vw,36rem)] overflow-y-auto border-l border-r border-border bg-background shadow-lg lg:block">
                <AlbumTrackDetails
                  album={displayAlbum}
                  searchTerm={searchTerm}
                  searchMatches={displayAlbum.searchMatches}
                  onFilterSelect={onFilterSelect}
                  variant="panel"
                />
              </aside>
            ) : null}

            <div className="h-full overflow-y-auto">
              <AlbumSidePanel
                album={displayAlbum}
                searchTerm={searchTerm}
                onFilterSelect={onFilterSelect}
                onAlbumUpdated={onAlbumUpdated}
                onAlbumDeleted={onAlbumDeleted}
                onDataChanged={onDataChanged}
                trackDetailsOpen={trackDetailsOpen}
                onTrackDetailsOpenChange={setTrackDetailsOpen}
              />
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default AlbumPanelSheet;
