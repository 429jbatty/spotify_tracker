import TimelineChart from "./AlbumsByDecadeChart";
import AlbumTable from "./AlbumTable";
import AlbumTimeline from "./AlbumTimeline";
import React, { useState, useMemo } from "react";

function AlbumTimeView({ albums }) {
  // local filter state: null = no filter
  const [filter, setFilter] = useState({ decade: null, year: null });

	const filteredAlbums = useMemo(() => {
	const albumsArray = Object.values(albums); // convert object to array
	if (!filter.decade) return albumsArray;

	return albumsArray.filter((a) => {
			if (!a.release_date) return false;
			const year = parseInt(a.release_date.slice(0, 4));
			if (filter.year) return year === filter.year;
			return Math.floor(year / 10) * 10 === filter.decade;
	});
	}, [albums, filter]);

  // Reset filter to show all
  const resetFilter = () => setFilter({ decade: null, year: null });

  return (
    <div>
      <h2>Album Dashboard</h2>
      <TimelineChart
        albums={albums}
        selectedFilter={filter}
        onSelect={(decade, year = null) => setFilter({ decade, year })}
        onReset={resetFilter}
      />
      <AlbumTable albums={filteredAlbums} />
    </div>
  );
}

export default AlbumTimeView;
