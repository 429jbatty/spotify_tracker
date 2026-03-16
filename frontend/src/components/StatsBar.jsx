import StatCard from "./StatCard";

function StatsBar({ albums }) {
  const albumList = Object.values(albums);
  const totalAlbums = albumList.length;
  const artistSet = new Set(albumList.map(a => a.artist));
  const totalArtists = artistSet.size;
  const avgAlbumsPerArtist =
    totalArtists === 0 ? 0 : (totalAlbums / totalArtists).toFixed(2);

  return (
    <div className="flex flex-col md:flex-row gap-3 mb-8">
      <StatCard title="Total Albums" value={totalAlbums} />
      <StatCard title="Total Artists" value={totalArtists}/>
      <StatCard title="Avg Albums/Artist" value={avgAlbumsPerArtist}/>
    </div>
  );
}

export default StatsBar;