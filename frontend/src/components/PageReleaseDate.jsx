import React, { useState, useMemo } from "react";
import ReleaseDateChart from "./ReleaseDateChart";
import AlbumTable from "./AlbumTable";
import AlbumTimeline from "@/components/timeline/AlbumTimeline";
import AlbumPanelSheet from "./AlbumPanelSheet";

function AlbumTimeView({ albums, onFilterSelect, onDataChanged }) {
  const [filter, setFilter] = useState({ decade: null, year: null });
  const [chartMode, setChartMode] = useState("decade"); // "decade" or "year"
  const [selectedAlbum, setSelectedAlbum] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);

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
  const openAlbum = (album) => {
    setSelectedAlbum(album);
    setPanelOpen(true);
  };

  const updateSelectedAlbum = (album) => {
    setSelectedAlbum((current) => (current ? { ...current, ...album } : album));
  };

  const handleAlbumDeleted = () => {
    setSelectedAlbum(null);
    setPanelOpen(false);
  };

  return (
    <>
      <div className="space-y-10 px-6">
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
        <AlbumTimeline albums={filteredAlbums} onAlbumClick={openAlbum} />
        <div>
          <AlbumTable
            albums={filteredAlbums}
            onFilterSelect={onFilterSelect}
            onDataChanged={onDataChanged}
          />
        </div>
      </div>

      <AlbumPanelSheet
        open={panelOpen}
        onOpenChange={setPanelOpen}
        album={selectedAlbum}
        onFilterSelect={onFilterSelect}
        onAlbumUpdated={updateSelectedAlbum}
        onAlbumDeleted={handleAlbumDeleted}
        onDataChanged={onDataChanged}
      />
    </>
  );
}

export default AlbumTimeView;
