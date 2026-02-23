function AlbumCard({ albumId, album }) {
  return (
    <div
      style={{
        border: "1px solid #ccc",
        padding: "1rem",
        borderRadius: "8px",
      }}
    >
      {/* Album Artwork */}
      {album.image_url && (
        <img
          src={album.image_url}
          alt={album.name}
          style={{
            height: "200px",      // fixed height
            width: "auto",        // width adjusts to preserve aspect ratio
            borderRadius: "6px",
            marginBottom: "0.75rem",
            objectFit: "cover"    // ensures the image fills the box nicely if you use both width & height
          }}
        />
      )}

      <h2>{album.name}</h2>

      <div style={{ fontSize: "0.9rem", marginTop: "0.5rem" }}>
        {Object.entries(album).map(([key, value]) => {
          if (key === "name" || key === "image_url") return null; // because these were already used we don't want to display them

          return (
            <div key={key}>
              <strong>{formatKey(key)}:</strong> {String(value)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatKey(key) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default AlbumCard;