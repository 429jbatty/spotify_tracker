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
    <div style={{ marginTop: "2rem" }}>
      <h2>Recently Listened Albums</h2>
      <AlbumCardList albums={recentAlbums} />
    </div>
  );
}

export default RecentAlbums;