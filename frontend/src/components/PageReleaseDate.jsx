import React, { useState, useMemo } from "react";
import ReleaseDateChart from "./ReleaseDateChart";
import AlbumTable from "./AlbumTable";
import ChartToggleButton from "./ChartToggleButton";

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
    <div>
      <h2>Release Dates</h2>
      <ChartToggleButton mode={chartMode} onToggle={() => setChartMode(chartMode === "decade" ? "year" : "decade")} />
      <ReleaseDateChart
        albums={albums}
        selectedFilter={filter}
        onSelect={(decade, year = null) => setFilter({ decade, year })}
        onReset={resetFilter}
        chartMode={chartMode}
      />
      <AlbumTable albums={filteredAlbums} />
    </div>
  );
}

export default AlbumTimeView;