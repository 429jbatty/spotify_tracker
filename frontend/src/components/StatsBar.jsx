import StatCard from "./StatCard";

function StatsBar({ albums }) {
  const albumList = Object.values(albums);
  const totalAlbums = albumList.length;
  const artistSet = new Set(albumList.map(a => a.artist));
  const totalArtists = artistSet.size;
  const avgAlbumsPerArtist =
    totalArtists === 0
      ? 0
      : (totalAlbums / totalArtists).toFixed(2);

  const stats = {
    totalAlbums,
    totalArtists,
    avgAlbumsPerArtist,
  };

  return (
    <div style={{ display: "flex", gap: "1rem", marginBottom: "2rem" }}>
      <StatCard title="Total Albums" value={stats.totalAlbums} />
      <StatCard title="Total Artists" value={stats.totalArtists} />
      <StatCard title="Avg Albums/Artist" value={stats.avgAlbumsPerArtist} />
    </div>
  );
}

export default StatsBar;