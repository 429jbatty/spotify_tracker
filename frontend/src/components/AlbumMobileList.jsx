import { useState } from "react";
import { Button } from "@/components/ui/button";
import { getSourceLabel } from "./utils/sourceLabels";

const PAGE_SIZE = 50;

function formatDate(isoString) {
  if (!isoString) return "Unknown";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return `${date.getMonth() + 1}/${String(date.getDate()).padStart(2, "0")}/${date.getFullYear()}`;
}

function AlbumMobileList({ albums, sortBy, ascending, onSortChange, onOpenAlbum }) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const visibleAlbums = albums.slice(0, visibleCount);
  const hasMore = visibleAlbums.length < albums.length;

  return (
    <section className="md:hidden" aria-label="Album library">
      <label className="mb-3 flex items-center justify-between gap-3 text-sm font-medium text-foreground">
        <span>Sort library</span>
        <select
          value={`${sortBy}:${ascending ? "asc" : "desc"}`}
          onChange={(event) => {
            const [nextSortBy, direction] = event.target.value.split(":");
            onSortChange(nextSortBy, direction === "asc");
          }}
          className="min-h-11 rounded-md border border-input bg-background px-3 text-sm text-foreground"
          aria-label="Sort library"
        >
          <option value="latestListen:desc">Last listen, newest</option>
          <option value="latestListen:asc">Last listen, oldest</option>
          <option value="name:asc">Album, A–Z</option>
          <option value="name:desc">Album, Z–A</option>
          <option value="artist:asc">Artist, A–Z</option>
          <option value="artist:desc">Artist, Z–A</option>
          <option value="release_year:desc">Release year, newest</option>
          <option value="release_year:asc">Release year, oldest</option>
          <option value="totalListens:desc">Listens, most</option>
          <option value="totalListens:asc">Listens, fewest</option>
        </select>
      </label>

      <div className="space-y-3">
        {visibleAlbums.map((album) => (
          <button
            key={album.id}
            type="button"
            onClick={() => onOpenAlbum(album)}
            className="grid w-full grid-cols-[4rem_minmax(0,1fr)] gap-3 rounded-lg border border-border bg-card p-3 text-left shadow-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <img
              loading="lazy"
              src={album.image_url || `${import.meta.env.BASE_URL}placeholder_art.png`}
              onError={(event) => {
                event.currentTarget.onerror = null;
                event.currentTarget.src = `${import.meta.env.BASE_URL}placeholder_art.png`;
              }}
              className="size-16 rounded-md border border-border object-cover"
              alt=""
            />
            <span className="min-w-0">
              <span className="block break-words font-medium text-foreground">{album.name}</span>
              <span className="mt-0.5 block break-words text-sm text-muted-foreground">{album.artist}</span>
              <span className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>Last listened: {formatDate(album.latestListen)}</span>
                <span>Listens: {album.totalListens ?? 0}</span>
                <span>Released: {album.release_year || "Unknown"}</span>
                <span>Source: {getSourceLabel(album.entry_source || album.source)}</span>
                <span className="col-span-2 break-words">Label: {album.label || "Unknown"}</span>
              </span>
            </span>
          </button>
        ))}
      </div>

      {albums.length === 0 && (
        <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          No albums match the current filters.
        </p>
      )}

      {hasMore && (
        <div className="mt-4 text-center">
          <p className="mb-2 text-xs text-muted-foreground">
            Showing {visibleAlbums.length} of {albums.length} albums
          </p>
          <Button type="button" variant="outline" className="min-h-11" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>
            Load 50 more albums
          </Button>
        </div>
      )}
    </section>
  );
}

export default AlbumMobileList;
