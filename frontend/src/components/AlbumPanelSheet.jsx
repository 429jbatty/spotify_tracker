import { useState } from "react";
import AlbumSidePanel from "./AlbumSidePanel";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

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
  const [wideModeState, setWideModeState] = useState({
    albumId: null,
    open: false,
  });
  const albumId = album?.id || null;
  const hasCreditSearchMatches = (album?.searchMatches || []).some(
    (match) => match.type === "credit"
  );
  const wideMode = Boolean(
    open &&
    albumId &&
    (wideModeState.albumId === albumId ? wideModeState.open : hasCreditSearchMatches)
  );
  const setWideMode = (nextOpen) => {
    setWideModeState({ albumId, open: nextOpen });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className={cn(
          "!w-[min(100vw,42rem)] !max-w-none overflow-y-auto p-0 sm:!w-[42rem] sm:!max-w-none",
          wideMode && "lg:!w-[min(92vw,88rem)] xl:!w-[min(88vw,96rem)]"
        )}
      >
        <SheetTitle className="sr-only">
          {album?.name ? `${album.name} details` : "Album details"}
        </SheetTitle>
        {album && (
          <AlbumSidePanel
            album={album}
            searchTerm={searchTerm}
            onFilterSelect={onFilterSelect}
            onAlbumUpdated={onAlbumUpdated}
            onAlbumDeleted={onAlbumDeleted}
            onDataChanged={onDataChanged}
            trackDetailsOpen={wideMode}
            onTrackDetailsOpenChange={setWideMode}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}

export default AlbumPanelSheet;
