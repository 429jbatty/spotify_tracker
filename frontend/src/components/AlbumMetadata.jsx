import AlbumInfoRow from "./AlbumInfoRow";
import { createAlbumFilter } from "./utils/albumFilters";
import { getSourceLabel } from "./utils/sourceLabels";

function FilterChip({ children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md border border-border px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
    >
      {children}
    </button>
  );
}

function AlbumMetadata({ album, onFilterSelect }) {
  const genres = Array.from(new Set(album.genres || [])).slice(0, 10);
  const decade = album.release_year
    ? Math.floor(Number(album.release_year) / 10) * 10
    : null;

  return (
    <div className="space-y-3">
      <AlbumInfoRow
        label="Release"
        value={album.release_date}
        color="primary"
      />
      <AlbumInfoRow
        label="Label"
        value={album.label}
        color="muted"
      />
      <AlbumInfoRow
        label="Source"
        value={getSourceLabel(album.entry_source || album.source)}
        color="accent"
      />

      {onFilterSelect && (
        <div className="flex flex-wrap gap-2 pt-1">
          {album.label && (
            <FilterChip
              onClick={() =>
                onFilterSelect(createAlbumFilter("label", album.label, album.label))
              }
            >
              {album.label}
            </FilterChip>
          )}

          {album.release_year && (
            <FilterChip
              onClick={() =>
                onFilterSelect(
                  createAlbumFilter("year", album.release_year, String(album.release_year))
                )
              }
            >
              {album.release_year}
            </FilterChip>
          )}

          {(album.entry_source || album.source) && (
            <FilterChip
              onClick={() =>
                onFilterSelect(
                  createAlbumFilter(
                    "entry-source",
                    album.entry_source || album.source,
                    getSourceLabel(album.entry_source || album.source)
                  )
                )
              }
            >
              {getSourceLabel(album.entry_source || album.source)}
            </FilterChip>
          )}

          {decade && (
            <FilterChip
              onClick={() =>
                onFilterSelect(createAlbumFilter("decade", decade, `${decade}s`))
              }
            >
              {decade}s
            </FilterChip>
          )}

          {genres.map((genre) => (
            <FilterChip
              key={genre}
              onClick={() => onFilterSelect(createAlbumFilter("genre", genre, genre))}
            >
              {genre}
            </FilterChip>
          ))}
        </div>
      )}
    </div>
  );
}

export default AlbumMetadata;
