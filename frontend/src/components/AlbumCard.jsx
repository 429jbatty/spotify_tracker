function AlbumCard({ album }) {
  // Define the fields and order you want to display
  const metadataForCard = [
    "artist",
    "release_date",
    "label",
    "total_tracks",
    "listen_date",
    "source"
  ];

  return (
    <div
      style={{
        border: "1px solid #ccc",
        padding: "1rem",
        borderRadius: "8px",
      }}
    >
      {/* Album Artwork */}
      <img
        src={album.image_url || "/placeholder_art.png"}
        onError={(e) => {
          e.target.onerror = null;
          e.target.src = "/placeholder_art.png";
        }}
        style={{
          height: "200px",      // fixed height
          width: "auto",        // width adjusts to preserve aspect ratio
          borderRadius: "6px",
          marginBottom: "0.75rem",
          objectFit: "cover"
        }}
      />

      <h2>{album.name}</h2>

      <div style={{ fontSize: "0.9rem", marginTop: "0.5rem" }}>
        {metadataForCard.map((key) => {
          const value = album[key];
          if (value === undefined || value === null) return null;
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