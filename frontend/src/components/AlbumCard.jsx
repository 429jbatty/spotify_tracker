import { useState } from "react";

// Helper function to group album credits by category
function groupAlbumCredits(album) {

  const categories = {
    Engineers: ["engineer", "mix"],
    Instrumentation: ["instrument"],
    Producer: ["producer"],
    Other: [],
  };

  const grouped = {
    Engineers: {},
    Instrumentation: {},
    Producer: {},
    Other: {},
  };

  for (const track of album.tracklist || []) {
    const credits = Array.isArray(track.credits) ? track.credits : [];
    for (const credit of credits) {
      if (!Array.isArray(credit) || credit.length < 3) continue;
      const [name, role, detail] = credit;
      const roleDetail = detail ? `${role}, ${detail}` : role;

      // Determine category
      let category = "Other";
      for (const [catName, roles] of Object.entries(categories)) {
        if (roles.includes(role.toLowerCase())) {
          category = catName;
          break;
        }
      }

      // Initialize person entry if needed
      if (!grouped[category][name]) grouped[category][name] = new Set();
      grouped[category][name].add(roleDetail);
    }
  }

  // Convert Sets to arrays for rendering
  for (const category of Object.keys(grouped)) {
    for (const person of Object.keys(grouped[category])) {
      grouped[category][person] = Array.from(grouped[category][person]);
    }
  }

  return grouped;
}

function AlbumCard({ album }) {
  const [creditsOpen, setCreditsOpen] = useState(false);
  const groupedCredits = groupAlbumCredits(album);
  const BASE = import.meta.env.BASE_URL;

  return (
    <div
      style={{
        border: "1px solid #ccc",
        padding: "1rem",
        borderRadius: "8px",
        marginBottom: "1rem",
      }}
    >
      {/* Album Artwork */}
      <img
        src={album.image_url || `${BASE}placeholder_art.png`}
        onError={(e) => {
          e.target.onerror = null;
          e.target.src = `${BASE}placeholder_art.png`;
        }}
        style={{
          height: "200px",
          width: "auto",
          borderRadius: "6px",
          marginBottom: "0.75rem",
          objectFit: "cover",
        }}
      />

      <h2>{album.name}</h2>

      <div style={{ fontSize: "0.9rem", marginTop: "0.5rem" }}>
        <div>
          <strong>Artist:</strong> {album.artist}
        </div>
        <div>
          <strong>Release Date:</strong> {album.release_date}
        </div>
        <div>
          <strong>Label:</strong> {album.label}
        </div>
      </div>

      {/* Collapsible Credits */}
      <div style={{ marginTop: "1rem" }}>
        <button
          onClick={() => setCreditsOpen(!creditsOpen)}
          style={{
            cursor: "pointer",
            padding: "0.25rem 0.5rem",
            fontSize: "0.9rem",
            borderRadius: "4px",
            border: "1px solid #888",
            backgroundColor: "#f0f0f0",
          }}
        >
          {creditsOpen ? "Hide Credits" : "Show Credits"}
        </button>

        {creditsOpen && (
          <div style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
            {Object.entries(groupedCredits).map(([groupName, persons]) => {
              if (Object.keys(persons).length === 0) return null;
              return (
                <div key={groupName} style={{ marginTop: "0.5rem" }}>
                  <strong>{groupName}:</strong>
                  {Object.entries(persons).map(([name, roles]) => (
                    <div key={name}>
                      {name} (
                      {roles.join(", ")}
                      )
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default AlbumCard;