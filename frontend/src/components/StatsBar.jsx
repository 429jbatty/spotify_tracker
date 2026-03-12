import StatCard from "./StatCard";

function StatsBar({ albums }) {
  const albumList = Object.values(albums);
  const totalAlbums = albumList.length;
  const artistSet = new Set(albumList.map(a => a.artist));
  const totalArtists = artistSet.size;
  const avgAlbumsPerArtist =
    totalArtists === 0 ? 0 : (totalAlbums / totalArtists).toFixed(2);

  return (
    <div className="flex flex-col md:flex-row gap-4 mb-8">
      <StatCard title="Total Albums" value={totalAlbums} color="text-orange-500" />
      <StatCard title="Total Artists" value={totalArtists} color="text-neutral-500" />
      <StatCard title="Avg Albums/Artist" value={avgAlbumsPerArtist} color="text-neutral-500" />
    </div>
  );
}

export default StatsBar;