import AlbumCard from "./AlbumCard";

function AlbumList({ albums }) {
  const albumArray = Object.entries(albums || {});

  if (albumArray.length === 0) {
    return <p>No completed albums yet.</p>;
  }

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {albumArray.map(([albumId, albumData]) => (
        <AlbumCard key={albumId} albumId={albumId} album={albumData} />
      ))}
    </div>
  );
}

export default AlbumList;