import React from "react";

function AlbumTimeline({ albums }) {
  // Convert albums object to array and sort by release date
  const albumArray = Object.entries(albums)
    .map(([id, album]) => ({ id, ...album }))
    .sort(
      (a, b) => new Date(a.release_date) - new Date(b.release_date)
    );

  return (
    <div
      style={{
        display: "flex",
        overflowX: "auto",
        padding: "1rem",
        border: "1px solid #ccc",
        borderRadius: "8px",
      }}
    >
      {albumArray.map((album) => (
        <div
          key={album.id}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            marginRight: "1rem",
            minWidth: "100px",
          }}
        >
          {/* Album artwork */}
          <img
            src={album.image_url || "/placeholder_art.png"}
            onError={(e) => {
              e.target.onerror = null;
              e.target.src = "/placeholder_art.png";
            }}
            style={{
              width: "100px",
              height: "100px",
              objectFit: "cover",
              borderRadius: "4px",
              marginBottom: "0.5rem",
            }}
          />

          {/* Album name */}
          <div style={{ fontSize: "0.8rem", textAlign: "center" }}>
            {album.name}
          </div>

          {/* Release date */}
          <div style={{ fontSize: "0.7rem", color: "#555" }}>
            {new Date(album.release_date).toLocaleDateString()}
          </div>
        </div>
      ))}
    </div>
  );
}

export default AlbumTimeline;