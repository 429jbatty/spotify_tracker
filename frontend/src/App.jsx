import { useEffect, useState } from "react";
import AlbumCardList from "./components/AlbumCardList";
import AlbumTable from "./components/AlbumTable";
import AlbumTimeView from "./components/PageReleaseDate";
import AlbumSearch from "./components/AlbumSearch";
import Dashboard from "./components/Dashboard";
import normalizeAlbums from "./services/albumNormalizer";
import ViewSwitcher from "./components/ViewSwitcher";

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState("table"); // "table", "card", "timeline", "dashboard"
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}album_state.json`)
      .then((res) => {
        if (!res.ok) {
          throw new Error("Failed to fetch album data");
        }
        return res.json();
      })
      .then((json) => {
        console.log("Loaded JSON:", json);
        setData({
          ...json,
          completed_albums: normalizeAlbums(json.completed_albums)
        });
      })
      .catch((err) => {
        console.error(err);
        setError(err.message);
      });
  }, []);

  if (error) return <div>Error: {error}</div>;
  if (!data) return <div>Loading...</div>;

  {/*Search functionality*/}
  const filteredAlbums = Object.fromEntries(
    Object.entries(data.completed_albums).filter(([id, album]) => {
      const term = searchTerm.toLowerCase();
      return (
        album.name.toLowerCase().includes(term) ||
        album.artist.toLowerCase().includes(term)
      );
    })
  );

  return (
    <div style={{ padding: "2rem" }}>
      <h1>Completed Albums</h1>
      <ViewSwitcher view={view} setView={setView} />

      {/* search box (don't render on dashboard) */}
      {view !== "dashboard" && (
        <AlbumSearch searchTerm={searchTerm} setSearchTerm={setSearchTerm} />
      )}

      {/* Conditional rendering based on selected view */}
      {view === "dashboard" && <Dashboard albums={data.completed_albums} ids={data.most_recently_listened} />}
      {view === "table" && <AlbumTable albums={filteredAlbums}/>}
      {view === "card" && <AlbumCardList albums={filteredAlbums}/>}
      {view === "timeline" && <AlbumTimeView albums={filteredAlbums}/>}
    </div>
  );
}

export default App;