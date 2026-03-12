import AlbumCardList from "./AlbumCardList";

function RecentAlbums({ albums, ids }) {

  const numberRecentAlbums = 6;

  const recentAlbums = ids
    .slice(0, numberRecentAlbums)
    .map(id => {
      const album = albums[id];
      if (!album) return null;

      return {
        id,
        ...album
      };
    })
    .filter(Boolean);

  return (
  <div className="mt-12 px-6">
    <h2 className="text-3xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-gray-700 via-gray-600 to-gray-700 drop-shadow-md mb-6">
      Recent listens
    </h2>
    <AlbumCardList albums={recentAlbums} />
  </div>
  );
}

export default RecentAlbums;