import AlbumCard from "./AlbumCard";

function AlbumCardList({ albums }) {
  const albumArray = Object.entries(albums || {});

  if (albumArray.length === 0) {
    return <p>No completed albums yet.</p>;
  }

  return (
    <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(3, 1fr)" }}>
      {albumArray.map(([albumId, albumData]) => (
        <AlbumCard key={albumId} albumId={albumId} album={albumData} />
      ))}
    </div>
  );
}

export default AlbumCardList;