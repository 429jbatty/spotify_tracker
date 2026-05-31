export const IMPORT_GUIDES = {
  lastfm: {
    title: "Last.fm import",
    intro: "Use a public Last.fm username. Albumary stores scrobbles, then only adds completed album listens.",
    points: [
      "Preview is a fast sample.",
      "Imports continue in the background.",
      "Singles and partial listens are not added as albums.",
    ],
    exampleLabel: "Example",
    example: "Username: your-lastfm-name",
  },
  spotify_import: {
    title: "Spotify ZIP import",
    intro: "Upload the Extended Streaming History ZIP from Spotify. Albumary stores plays first, then only adds completed album listens.",
    points: [
      "Upload the ZIP without extracting it.",
      "Imports continue in the background.",
      "Partial plays are stored but not added as albums.",
    ],
    exampleLabel: "Expected file",
    example: "my_spotify_data.zip",
  },
};

export function summaryCards(source, summary) {
  if (!summary) return [];
  if (source === "spotify_import") {
    return [
      { label: "Spotify Plays Found", value: summary.total_rows },
      { label: "New Plays Stored", value: summary.new_event_rows },
      { label: "Album Sessions", value: summary.distinct_album_candidates },
      { label: "Already Imported", value: summary.duplicate_rows },
    ];
  }
  return [
    { label: "Last.fm Scrobbles Found", value: summary.total_rows },
    { label: "New in Preview Sample", value: summary.new_event_rows },
    { label: "Album Sessions in Sample", value: summary.distinct_album_candidates },
    { label: "Already Imported in Sample", value: summary.duplicate_rows },
  ];
}

export function previewSummaryNote(summary) {
  if (!summary) return null;

  const details = [];
  if (summary.missing_album_rows > 0) {
    details.push(`${summary.missing_album_rows.toLocaleString()} scrobbles in the preview sample are missing album names`);
  }
  if (summary.review_candidates > 0) {
    details.push(`${summary.review_candidates.toLocaleString()} possible album sessions may need review after import`);
  }
  if ((summary.pending_metadata_candidates || 0) > 0) {
    details.push(`${summary.pending_metadata_candidates.toLocaleString()} possible album sessions need tracklists before they can be judged`);
  }

  if (!details.length) {
    return "Preview is a fast sample. Album listens are finalized after the background import stores scrobbles and checks album tracklists.";
  }

  return `Preview is a fast sample. ${details.join(". ")}. Album listens are finalized after background matching.`;
}

export function importSummaryText(summary, status) {
  if (!summary) return "";

  const events = Number(summary.new_event_rows || 0).toLocaleString();
  const listens = Number(summary.derived_album_listens || 0).toLocaleString();
  const review = Number(summary.review_candidates || 0).toLocaleString();
  const pending = Number(summary.pending_metadata_candidates || 0).toLocaleString();

  if (["completed", "failed"].includes(status)) {
    const reviewText = summary.review_candidates
      ? ` ${review} unresolved album sessions need review.`
      : "";
    return `${events} import rows stored. ${listens} album listens created.${reviewText}`;
  }

  const pendingText = summary.pending_metadata_candidates
    ? ` ${pending} album sessions still need tracklists.`
    : "";
  return `${events} import rows stored so far. ${listens} album listens created so far.${pendingText}`;
}

export function formatDuration(seconds) {
  const total = Number(seconds || 0);
  if (!total || total < 1) return "0s";
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = Math.floor(total % 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

export function currentStepPercent(item) {
  const step = item?.steps?.find((entry) => entry.key === item.current_step_key);
  const total = Number(step?.total || item?.summary?.progress_total || 0);
  const current = Number(step?.current || item?.summary?.progress_current || 0);
  if (!total || total <= 0) return null;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

export function importDiagnostics(item) {
  const summary = item?.summary || {};
  return [
    { label: "Rows stored", value: summary.new_event_rows },
    { label: "Album sessions", value: summary.distinct_album_candidates },
    { label: "Album listens", value: summary.derived_album_listens },
    { label: "Review", value: summary.review_candidates },
    { label: "MB lookups", value: summary.musicbrainz_requests },
    { label: "Cache hits", value: summary.metadata_cache_hits },
    {
      label: "Avg lookup",
      value: summary.musicbrainz_lookup_seconds_avg
        ? `${Number(summary.musicbrainz_lookup_seconds_avg).toFixed(1)}s`
        : null,
    },
    {
      label: "ETA",
      value: item?.estimated_seconds_remaining
        ? formatDuration(item.estimated_seconds_remaining)
        : null,
    },
  ].filter((entry) => entry.value !== null && entry.value !== undefined);
}
