import { useEffect, useState } from "react";
import AlbumCardList from "./components/AlbumCardList";
import AlbumTable from "./components/AlbumTable";
import AlbumTimeline from "./AlbumTimeline";
import AlbumSearch from "./components/AlbumSearch";

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState("table"); // "table" or "card"
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    fetch("/album_state.json")
      .then((res) => {
        if (!res.ok) {
          throw new Error("Failed to fetch album data");
        }
        return res.json();
      })
      .then((json) => {
        console.log("Loaded JSON:", json); // Debug visibility
        setData(json);
      })
      .catch((err) => {
        console.error(err);
        setError(err.message);
      });
  }, []);

  if (error) return <div>Error: {error}</div>;
  if (!data) return <div>Loading...</div>;

  const buttonStyle = (isActive) => ({
    marginRight: "0.5rem",
    padding: "0.5rem 1rem",
    cursor: "pointer",
    backgroundColor: isActive ? "#007bff" : "#f0f0f0",
    color: isActive ? "white" : "black",
    border: "none",
    borderRadius: "4px",
  });

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

      {/* View toggle buttons */}
      <div style={{ marginBottom: "1rem" }}>
        <button
          onClick={() => setView("table")}
          style={buttonStyle(view === "table")}
        >
          Table View
        </button>
        <button
          onClick={() => setView("card")}
          style={buttonStyle(view === "card")}
        >
          Card View
        </button>
        <button
          onClick={() => setView("timeline")}
          style={buttonStyle(view === "timeline")}
        >
          Timeline View
        </button>
      </div>

      {/*search box */}
      <AlbumSearch searchTerm={searchTerm} setSearchTerm={setSearchTerm} />

      {/* Conditional rendering based on selected view */}
      {view === "table" && <AlbumTable albums={filteredAlbums}/>}
      {view === "card" && <AlbumCardList albums={filteredAlbums}/>}
      {view === "timeline" && <AlbumTimeline albums={filteredAlbums}/>}
    </div>
  );
}

export default App;