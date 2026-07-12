// albumNormalizer.jsx

function normalizeCredit(credit) {
  if (Array.isArray(credit) && credit.length >= 3) {
    return [credit[0], credit[1], credit[2]];
  }

  if (credit && typeof credit === "object") {
    const name = credit.name || credit.artist || "";
    const role = credit.role || credit.raw_credit_type || credit.type || "";
    const detail = Array.isArray(credit.attributes)
      ? credit.attributes.join(", ")
      : credit.attributes || credit.detail || "";

    if (name && role) {
      return [name, role, detail];
    }
  }

  return null;
}

function normalizeTrackCredits(track) {
  if (!Array.isArray(track?.credits)) {
    return track;
  }

  return {
    ...track,
    credits: track.credits.map(normalizeCredit).filter(Boolean),
  };
}

/**
 * Aggregate all track-level credits into a single album-level array.
 * Each display credit is an array: [name, role, detail]
 */
function aggregateAlbumCredits(album) {
  const seen = new Set();
  const allCredits = [];

  for (const track of album.tracklist || []) {
    const credits = Array.isArray(track.credits) ? track.credits : [];
    for (const credit of credits) {
      const normalizedCredit = normalizeCredit(credit);
      if (normalizedCredit) {
        const key = `${normalizedCredit[0]}||${normalizedCredit[1]}||${normalizedCredit[2]}`;
        if (seen.has(key)) continue;
        seen.add(key);
        allCredits.push(normalizedCredit);
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
  const tracklist = Array.isArray(album.tracklist)
    ? album.tracklist.map(normalizeTrackCredits)
    : album.tracklist;
  const normalizedAlbum = {
    ...album,
    tracklist,
  };
  const album_credits = aggregateAlbumCredits(normalizedAlbum);

  return {
    ...normalizedAlbum,
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
