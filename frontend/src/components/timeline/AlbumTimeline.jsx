import { useMemo } from "react";
import YearNode from "./YearNode";

function AlbumTimeline({ albums, onAlbumClick }) {
  const grouped = useMemo(() => {
    const groups = {};

    Object.values(albums).forEach((album) => {
      const year = album.release_year;
      if (!groups[year]) groups[year] = [];
      groups[year].push(album);
    });

    return Object.entries(groups)
      .map(([year, albums]) => ({
        year: Number(year),
        albums,
      }))
      .sort((a, b) => b.year - a.year);
  }, [albums]);

  return (
    <div className="relative mx-auto max-w-3xl py-20">
      {/* timeline spine */}
      <div className="absolute left-1/2 top-0 h-full w-px bg-border" />

      <div className="space-y-28">
        {grouped.map((yearGroup) => (
          <YearNode
            key={yearGroup.year}
            year={yearGroup.year}
            albums={yearGroup.albums}
            onAlbumClick={onAlbumClick}
          />
        ))}
      </div>
    </div>
  );
}

export default AlbumTimeline;
