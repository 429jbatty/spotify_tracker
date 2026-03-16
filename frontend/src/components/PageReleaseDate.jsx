import React, { useState, useMemo } from "react";
import ReleaseDateChart from "./ReleaseDateChart";
import AlbumTable from "./AlbumTable";
import AlbumTimeline from "@/components/timeline/AlbumTimeline";

function AlbumTimeView({ albums }) {
  const [filter, setFilter] = useState({ decade: null, year: null });
  const [chartMode, setChartMode] = useState("decade"); // "decade" or "year"

  const filteredAlbums = useMemo(() => {
    const albumsArray = Object.values(albums);
    if (!filter.decade) return albumsArray;
    return albumsArray.filter((a) => {
      if (!a.release_date) return false;
      const year = parseInt(a.release_date.slice(0, 4));
      if (filter.year) return year === filter.year;
      return Math.floor(year / 10) * 10 === filter.decade;
    });
  }, [albums, filter]);

  const resetFilter = () => setFilter({ decade: null, year: null });

  return (
    <div className="space-y-10">
      <div>
        <ReleaseDateChart
          albums={albums}
          selectedFilter={filter}
          onSelect={(decade, year = null) => setFilter({ decade, year })}
          onReset={resetFilter}
          chartMode={chartMode}
          onToggle={(mode) => setChartMode(mode)} // <- parent controls state
          chartHeight={400}
        />
      </div>
      <div>
        <AlbumTable albums={filteredAlbums} />
      </div>
    </div>
  );
}

export default AlbumTimeView;