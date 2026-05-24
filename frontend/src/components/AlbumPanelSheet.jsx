import { useState } from "react";
import AlbumSidePanel from "./AlbumSidePanel";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

function AlbumPanelSheet({
  open,
  onOpenChange,
  album,
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
  const wideMode = open && wideModeState.albumId === albumId && wideModeState.open;
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
        {album && (
          <AlbumSidePanel
            album={album}
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
