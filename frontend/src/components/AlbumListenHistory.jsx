import { formatDate } from "./utils/albumHelpers";

function AlbumListenHistory({ listenStats }) {
  if (!listenStats) return null;

  return (
    <div className="border-t border-border pt-4 space-y-2">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>First: {formatDate(listenStats.first)}</span>
        <span>Last: {formatDate(listenStats.last)}</span>
      </div>
    </div>
  );
}

export default AlbumListenHistory;