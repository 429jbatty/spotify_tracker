import AlbumCardVertical from "./AlbumCardVertical";

function AlbumCardList({ albums }) {
  const albumArray = Object.entries(albums || {});

  if (albumArray.length === 0) {
    return <p className="text-foreground">No completed albums yet.</p>;
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