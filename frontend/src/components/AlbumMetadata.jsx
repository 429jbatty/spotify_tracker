import AlbumInfoRow from "./AlbumInfoRow";
import { createAlbumFilter } from "./utils/albumFilters";

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
  const tags = [...(album.genres || []), ...(album.tags || [])];
  const uniqueTags = Array.from(new Set(tags)).slice(0, 10);
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

          {decade && (
            <FilterChip
              onClick={() =>
                onFilterSelect(createAlbumFilter("decade", decade, `${decade}s`))
              }
            >
              {decade}s
            </FilterChip>
          )}

          {uniqueTags.map((tag) => (
            <FilterChip
              key={tag}
              onClick={() => onFilterSelect(createAlbumFilter("tag", tag, tag))}
            >
              {tag}
            </FilterChip>
          ))}
        </div>
      )}
    </div>
  );
}

export default AlbumMetadata;
