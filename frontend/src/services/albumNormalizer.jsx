// albumNormalizer.jsx

/**
 * Aggregate all track-level credits into a single album-level array.
 * Each credit is an array: [name, role, detail]
 */
function aggregateAlbumCredits(album) {
  const seen = new Set();
  const allCredits = [];

  for (const track of album.tracklist || []) {
    const credits = Array.isArray(track.credits) ? track.credits : [];
    for (const credit of credits) {
      if (Array.isArray(credit) && credit.length >= 3) {
        const key = `${credit[0]}||${credit[1]}||${credit[2]}`; // unique string key
        if (!seen.has(key)) {
          seen.add(key);
          allCredits.push([credit[0], credit[1], credit[2]]);
        }
      }
    }
  }

  return allCredits;
}

/**
 * Normalize raw albums JSON.
 * - Adds derived release_date
 * - Adds album-level album_credits
 */
export function normalizeAlbum(album) {
  if (!album || typeof album !== "object") {
    return album;
  }

  // Derived release_date (YYYY-MM-DD) for sorting and chart grouping.
  const release_date = album.release_year
    ? `${album.release_year}-${String(album.release_month || 1).padStart(2, "0")}-${String(album.release_day || 1).padStart(2, "0")}`
    : null;

  // Aggregate album-level credits
  const album_credits = aggregateAlbumCredits(album);

  return {
    ...album,
    release_date,
    album_credits, // array of arrays: [name, role, detail]
  };
}

function normalizeAlbums(rawAlbums) {
  if (!rawAlbums || typeof rawAlbums !== "object") {
    return {};
  }

  return Object.fromEntries(
    Object.entries(rawAlbums).map(([key, album]) => {
      return [key, normalizeAlbum(album)];
    })
  );
}

export default normalizeAlbums;
