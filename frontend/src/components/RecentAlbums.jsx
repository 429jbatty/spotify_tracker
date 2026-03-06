import AlbumCard from "./AlbumCard";
import AlbumCardList from "./AlbumCardList";

function RecentAlbums({ albums }) {
  
  // Number of recent albums to display
  const numberRecentAlbums = 6
  
  const recentAlbums = Object.entries(albums)
      .map(([id, album]) => ({ id, ...album }))
      .filter(a => a.listen_history)
      .sort((a, b) => new Date(b.listen_history) - new Date(a.listen_history))
      .slice(0, numberRecentAlbums);

  return (
    <div style={{ marginTop: "2rem" }}>
      <h2>Recently Listened Albums</h2>
      <AlbumCardList albums={recentAlbums} />
    </div>
  );
}

export default RecentAlbums;