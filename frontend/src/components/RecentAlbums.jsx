import AlbumCard from "./AlbumCard";

function RecentAlbums({ albums }) {
  const recentAlbums = Object.entries(albums)
      .map(([id, album]) => ({ id, ...album }))
      .filter(a => a.listen_date)
      .sort((a, b) => new Date(b.listen_date) - new Date(a.listen_date))
      .slice(0, 3);

  return (
    <div style={{ marginTop: "2rem" }}>
      <h2>Recently Listened Albums</h2>
      <div style={{ display: "flex", gap: "1rem", overflowX: "auto", marginTop: "1rem" }}>
        {recentAlbums.map(album => (
          <AlbumCard key={album.id} albumId={album.id} album={album} />
        ))}
      </div>
    </div>
  );
}

export default RecentAlbums;