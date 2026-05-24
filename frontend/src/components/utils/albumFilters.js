import { getUserTagLabel } from "./userTags";
import { getSourceLabel } from "./sourceLabels";

function normalize(value) {
  return String(value || "").toLowerCase();
}

function valueMatches(value, term) {
  return normalize(value).includes(term);
}

function normalizeTagList(values) {
  return (values || []).map((value) =>
    typeof value === "string"
      ? getUserTagLabel(value)
      : value?.label || getUserTagLabel(value?.id) || ""
  );
}

function addAlbumFieldMatch(matches, term, field, label, value) {
  if (!valueMatches(value, term)) return;

  matches.push({
    type: "album",
    field,
    label,
    value: String(value),
  });
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

export function getAlbumSearchMatches(album, searchTerm) {
  const term = normalize(searchTerm).trim();
  if (!term) return [];

  const matches = [];

  addAlbumFieldMatch(matches, term, "name", "album", album.name);
  addAlbumFieldMatch(matches, term, "artist", "artist", album.artist);
  addAlbumFieldMatch(matches, term, "label", "label", album.label);
  addAlbumFieldMatch(matches, term, "release_year", "release year", album.release_year);
  addAlbumFieldMatch(matches, term, "release_date", "release date", album.release_date);
  addAlbumFieldMatch(matches, term, "notes", "notes", album.notes);
  addAlbumFieldMatch(
    matches,
    term,
    "entry_source",
    "source",
    getSourceLabel(album.entry_source || album.source)
  );

  for (const genre of album.genres || []) {
    addAlbumFieldMatch(matches, term, "genre", "genre", genre);
  }

  for (const tag of normalizeTagList(album.your_tags)) {
    addAlbumFieldMatch(matches, term, "your_tag", "your tag", tag);
  }

  for (const track of album.tracklist || []) {
    if (!Array.isArray(track.credits)) continue;

    for (const credit of track.credits) {
      if (!Array.isArray(credit)) continue;

      const [name, role, detail] = credit;
      if (![name, role, detail].some((value) => valueMatches(value, term))) continue;

      matches.push({
        type: "credit",
        field: "credit",
        value: [name, role, detail].filter(Boolean).join(" - "),
        trackTitle: track.title,
        trackPosition: track.position,
        name,
        role,
        detail,
      });
    }
  }

  return matches;
}

export function albumMatchesSearch(album, searchTerm) {
  const term = normalize(searchTerm).trim();
  if (!term) return true;
  return getAlbumSearchMatches(album, searchTerm).length > 0;
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
  if (filter.type === "genre") {
    return (album.genres || []).some((genre) => normalize(genre) === value);
  }
  if (filter.type === "your-tag") {
    return normalizeTagList(album.your_tags).some((tag) => normalize(tag) === value);
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
  if (filter.type === "entry-source") {
    return normalize(album.entry_source || album.source) === value;
  }
  if (filter.type === "quality") return getQualityIssueIds(album).includes(filter.value);

  return true;
}

export function albumMatchesFilters(album, filters = []) {
  return filters.every((filter) => albumMatchesFilter(album, filter));
}

export function filterAlbums(albums, searchTerm, filters = []) {
  const term = normalize(searchTerm).trim();

  return albums.reduce((matchedAlbums, album) => {
    const searchMatches = term ? getAlbumSearchMatches(album, searchTerm) : [];
    if (term && searchMatches.length === 0) return matchedAlbums;
    if (!albumMatchesFilters(album, filters)) return matchedAlbums;

    matchedAlbums.push(term ? { ...album, searchMatches } : album);
    return matchedAlbums;
  }, []);
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
