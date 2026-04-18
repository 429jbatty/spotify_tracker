import { useMemo, useState } from "react";

function groupAlbumsByYear(albums) {
  const groups = {};

  Object.values(albums || {}).forEach((album) => {
    if (!album.release_year) return;
    const year = Number(album.release_year);
    if (!groups[year]) groups[year] = [];
    groups[year].push(album);
  });

  return Object.entries(groups)
    .map(([year, albumsForYear]) => ({
      year: Number(year),
      albums: albumsForYear.sort((a, b) =>
        String(a.artist).localeCompare(String(b.artist))
      ),
    }))
    .sort((a, b) => b.year - a.year);
}

function AlbumTile({ album, onClick }) {
  const BASE = import.meta.env.BASE_URL;

  return (
    <button
      type="button"
      onClick={onClick}
      className="group grid grid-cols-[3.5rem_1fr] gap-3 rounded-lg border border-border p-2 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="aspect-square overflow-hidden rounded-md bg-card">
        <img
          loading="lazy"
          src={album.image_url || `${BASE}placeholder_art.png`}
          alt={album.name}
          onError={(event) => {
            event.currentTarget.onerror = null;
            event.currentTarget.src = `${BASE}placeholder_art.png`;
          }}
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
        />
      </div>
      <div className="min-w-0 self-center">
        <p className="truncate text-sm font-medium text-foreground">{album.name}</p>
        <p className="truncate text-xs text-muted-foreground">{album.artist}</p>
        {album.label && (
          <p className="mt-1 truncate text-[11px] text-muted-foreground">
            {album.label}
          </p>
        )}
      </div>
    </button>
  );
}

function YearButton({ yearGroup, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left transition-colors ${
        active
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-muted hover:text-foreground"
      }`}
    >
      <span className="text-sm font-semibold">{yearGroup.year}</span>
      <span className="rounded-md bg-background/60 px-2 py-1 text-xs">
        {yearGroup.albums.length}
      </span>
    </button>
  );
}

function AlbumTimeline({ albums, onAlbumClick }) {
  const yearGroups = useMemo(() => groupAlbumsByYear(albums), [albums]);
  const [selectedYear, setSelectedYear] = useState(null);
  const resolvedSelectedYear = yearGroups.some((group) => group.year === selectedYear)
    ? selectedYear
    : yearGroups[0]?.year;
  const selectedGroup = yearGroups.find(
    (group) => group.year === resolvedSelectedYear
  );
  const mostCollectedYears = [...yearGroups]
    .sort((a, b) => b.albums.length - a.albums.length)
    .slice(0, 5);

  if (yearGroups.length === 0) return null;

  return (
    <section className="px-6">
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border p-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                Release Year Browser
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Jump to a year, then open any album in the side panel.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              {mostCollectedYears.map((group) => (
                <button
                  key={group.year}
                  type="button"
                  onClick={() => setSelectedYear(group.year)}
                  className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  {group.year} - {group.albums.length}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid min-h-[28rem] grid-cols-1 lg:grid-cols-[14rem_1fr]">
          <aside className="border-b border-border lg:border-b-0 lg:border-r">
            <div className="max-h-72 overflow-y-auto p-3 lg:max-h-[32rem]">
              <div className="space-y-1">
                {yearGroups.map((yearGroup) => (
                  <YearButton
                    key={yearGroup.year}
                    yearGroup={yearGroup}
                    active={yearGroup.year === resolvedSelectedYear}
                    onClick={() => setSelectedYear(yearGroup.year)}
                  />
                ))}
              </div>
            </div>
          </aside>

          <div className="p-4">
            <div className="mb-4 flex items-baseline justify-between gap-4">
              <div>
                <h3 className="text-3xl font-semibold text-foreground">
                  {selectedGroup?.year}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {selectedGroup?.albums.length || 0} albums
                </p>
              </div>
            </div>

            <div className="grid max-h-[32rem] grid-cols-1 gap-3 overflow-y-auto pr-1 md:grid-cols-2 xl:grid-cols-3">
              {selectedGroup?.albums.map((album) => (
                <AlbumTile
                  key={album.id || album.release_group_mbid || `${album.artist}-${album.name}`}
                  album={album}
                  onClick={() => onAlbumClick?.(album)}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default AlbumTimeline;
