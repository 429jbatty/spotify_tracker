function normalize(value) {
  return String(value || "").toLowerCase();
}

export function getAlbumCredits(album) {
  const credits = [];

  for (const track of album.tracklist || []) {
    if (!Array.isArray(track.credits)) continue;

    for (const credit of track.credits) {
      if (Array.isArray(credit)) credits.push(credit);
    }
  }

  return credits;
}

export function albumMatchesSearch(album, searchTerm) {
  const term = normalize(searchTerm).trim();
  if (!term) return true;

  const searchableValues = [
    album.name,
    album.artist,
    album.label,
    album.release_year,
    album.release_date,
    ...(album.tags || []),
    ...(album.genres || []),
  ];

  for (const [name, role, detail] of getAlbumCredits(album)) {
    searchableValues.push(name, role, detail);
  }

  return searchableValues.some((value) => normalize(value).includes(term));
}

export function createAlbumFilter(type, value, label = value) {
  return {
    id: `${type}:${value}`,
    type,
    value,
    label,
  };
}

export function albumMatchesFilter(album, filter) {
  const value = normalize(filter.value);

  if (filter.type === "label") return normalize(album.label) === value;
  if (filter.type === "tag") {
    return [...(album.tags || []), ...(album.genres || [])].some(
      (tag) => normalize(tag) === value
    );
  }
  if (filter.type === "year") return String(album.release_year) === String(filter.value);
  if (filter.type === "decade") {
    const year = Number(album.release_year);
    return Number.isFinite(year) && Math.floor(year / 10) * 10 === Number(filter.value);
  }
  if (filter.type === "credit") {
    return getAlbumCredits(album).some(([name]) => normalize(name) === value);
  }
  if (filter.type === "credit-role") {
    return getAlbumCredits(album).some(([, role]) => normalize(role) === value);
  }
  if (filter.type === "quality") return getQualityIssueIds(album).includes(filter.value);

  return true;
}

export function albumMatchesFilters(album, filters = []) {
  return filters.every((filter) => albumMatchesFilter(album, filter));
}

export function filterAlbums(albums, searchTerm, filters = []) {
  return albums.filter(
    (album) => albumMatchesSearch(album, searchTerm) && albumMatchesFilters(album, filters)
  );
}

export const QUALITY_ISSUES = [
  { id: "missing-artwork", label: "Missing or unresolved artwork" },
  { id: "missing-label", label: "Missing label" },
  { id: "missing-release-date", label: "Missing release date" },
  { id: "missing-tracklist", label: "Missing tracklist" },
  { id: "missing-credits", label: "Missing track credits" },
];

export function hasMissingArtwork(album) {
  const imageUrl = String(album.image_url || "").trim();

  if (!imageUrl) return true;
  if (imageUrl.toLowerCase().includes("placeholder")) return true;
  return false;
}

export function getQualityIssueIds(album) {
  const issues = [];
  const tracklist = album.tracklist || [];
  const hasCredits = tracklist.some(
    (track) => Array.isArray(track.credits) && track.credits.length > 0
  );

  if (hasMissingArtwork(album)) issues.push("missing-artwork");
  if (!album.label) issues.push("missing-label");
  if (!album.release_year) issues.push("missing-release-date");
  if (tracklist.length === 0) issues.push("missing-tracklist");
  if (!hasCredits) issues.push("missing-credits");

  return issues;
}
