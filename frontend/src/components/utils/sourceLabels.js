const SOURCE_LABELS = {
  manual: "Manual",
  spotify_sync: "Spotify Sync",
  csv_upload: "CSV Upload",
  lastfm_import: "Last.fm Import",
  spotify_export_upload: "Spotify Export Upload",
  unknown: "Unknown",
  musicbrainz: "MusicBrainz",
  csv: "CSV Upload",
  lastfm: "Last.fm Import",
  spotify_export: "Spotify Export Upload",
};

export function getSourceLabel(source) {
  const key = String(source || "").trim().toLowerCase();
  if (!key) return SOURCE_LABELS.unknown;
  return SOURCE_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
