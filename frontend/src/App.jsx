import { useCallback, useEffect, useState } from "react";
import AlbumTable from "./components/AlbumTable";
import AlbumTimeView from "./components/PageReleaseDate";
import AlbumSearch from "./components/AlbumSearch";
import { fetchAlbumState } from "./services/albumApi";
import normalizeAlbums from "./services/albumNormalizer";
import Header from "./components/universalHeader";
import PageDiscovery from "./components/PageDiscovery";
import PageDataQuality from "./components/PageDataQuality";
import { filterAlbums } from "./components/utils/albumFilters";

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState("discovery");
  const [searchTerm, setSearchTerm] = useState("");
  const [activeFilters, setActiveFilters] = useState([]);

  const loadAlbumState = useCallback(async () => {
    const json = await fetchAlbumState();
    const normalized = {
      ...json,
      completed_albums: normalizeAlbums(json.completed_albums)
    };
    setData(normalized);
    setError(null);
    return normalized;
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadAlbumState().catch((err) => {
      console.error(err);
      setError(err.message);
    });
  }, [loadAlbumState]);

  if (error) return <div>Error: {error}</div>;
  if (!data) return <div>Loading...</div>;

  // Pre-calculate total listens and latest listen for sorting purposes
  const processedAlbums = Object.entries(data.completed_albums).map(([id, data]) => {
    const history = data.listen_history || [];
    return {
      id,

      // core safe fields (critical fix)
      name: data.name ?? "Unknown Album",
      artist: data.artist ?? "Unknown Artist",

      ...data,
      totalListens: history.length,
      // We keep latestListen as a sortable string/date object
      latestListen: history.length ? [...history].sort().reverse()[0] : null,
    };
  });

  const visibleAlbums = filterAlbums(processedAlbums, searchTerm, activeFilters);
  const filteredAlbums = Object.fromEntries(
    visibleAlbums.map((album) => [album.id, album])
  );
  const handleFilterSelect = (filter) => {
    setActiveFilters((current) => {
      if (current.some((item) => item.id === filter.id)) return current;
      return [...current, filter];
    });
    setView("table");
  };

  const removeFilter = (filterId) => {
    setActiveFilters((current) => current.filter((filter) => filter.id !== filterId));
  };

  const clearFilters = () => {
    setSearchTerm("");
    setActiveFilters([]);
  };

  return (
    <div className="min-h-screen space-y-10 ">

      {/* vertical stack header and search bar */}
      <div className="flex flex-col gap-4">
        {/* Header with tabs */}
        <Header view={view} setView={setView} onDataChanged={loadAlbumState} />

        {/* Search box (skip on dashboard) */}
        {!(view === "dashboard" || view === "discovery") && (
          <div className="px-6">
            <AlbumSearch searchTerm={searchTerm} setSearchTerm={setSearchTerm} />
          </div>
        )}

        {(searchTerm || activeFilters.length > 0) && (
          <div className="flex flex-wrap items-center gap-2 px-6">
            {searchTerm && (
              <span className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground">
                Search: {searchTerm}
              </span>
            )}
            {activeFilters.map((filter) => (
              <button
                key={filter.id}
                type="button"
                onClick={() => removeFilter(filter.id)}
                className="rounded-md border border-border px-2 py-1 text-xs text-foreground hover:bg-muted"
              >
                {filter.label}
              </button>
            ))}
            <button
              type="button"
              onClick={clearFilters}
              className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {view === "discovery" && (
        <PageDiscovery
          albums={visibleAlbums}
          allAlbums={processedAlbums}
          onFilterSelect={handleFilterSelect}
          onDataChanged={loadAlbumState}
        />
      )}
      {view === "table" && (
        <AlbumTable
          albums={filteredAlbums}
          onFilterSelect={handleFilterSelect}
          onDataChanged={loadAlbumState}
        />
      )}
      {view === "timeline" && (
        <AlbumTimeView
          albums={filteredAlbums}
          onFilterSelect={handleFilterSelect}
          onDataChanged={loadAlbumState}
        />
      )}
      {view === "quality" && (
        <PageDataQuality
          albums={visibleAlbums}
          onDataChanged={loadAlbumState}
          onFilterSelect={handleFilterSelect}
        />
      )}
    </div>
  );
}

export default App;
