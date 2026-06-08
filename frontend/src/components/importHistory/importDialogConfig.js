export const IMPORT_GUIDES = {
  lastfm: {
    title: "Last.fm import",
    intro: "Enter a public Last.fm username. Completed album listens are added after matching.",
  },
  spotify_import: {
    title: "Spotify ZIP import",
    intro: "Upload Spotify's Extended Streaming History ZIP without extracting it.",
  },
};

export function summaryCards(source, summary) {
  if (!summary) return [];
  if (source === "spotify_import") {
    return [
      { label: "Plays found", value: summary.total_rows },
      { label: "Album sessions", value: summary.distinct_album_candidates },
    ];
  }
  return [
    { label: "Scrobbles found", value: summary.total_rows },
    { label: "Album sessions", value: summary.distinct_album_candidates },
  ];
}

export function previewSummaryNote(summary) {
  if (!summary) return null;

  const details = [];
  if (summary.missing_album_rows > 0) {
    details.push(`${summary.missing_album_rows.toLocaleString()} scrobbles are missing album names`);
  }
  if (summary.review_candidates > 0) {
    details.push(`${summary.review_candidates.toLocaleString()} album sessions may need review`);
  }
  if ((summary.pending_metadata_candidates || 0) > 0) {
    details.push(`${summary.pending_metadata_candidates.toLocaleString()} album sessions need metadata before matching`);
  }

  if (!details.length) {
    return "Ready to import. Album listens will be finalized in the background.";
  }

  return `Ready to import. ${details.join(". ")}.`;
}

export function importSummaryText(summary, status) {
  if (!summary) return "";

  const events = Number(summary.new_event_rows || 0).toLocaleString();
  const listens = Number(summary.derived_album_listens || 0).toLocaleString();
  const review = Number(summary.review_candidates || 0).toLocaleString();
  const pending = Number(summary.pending_metadata_candidates || 0).toLocaleString();

  if (["completed", "failed"].includes(status)) {
    const reviewText = summary.review_candidates
      ? ` ${review} need review.`
      : "";
    return `${events} rows stored. ${listens} album listens created.${reviewText}`;
  }

  const pendingText = summary.pending_metadata_candidates
    ? ` ${pending} album sessions still need tracklists.`
    : "";
  return `${events} rows stored. ${listens} album listens created.${pendingText}`;
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

export function advancedImportStats(item) {
  const summary = item?.summary;
  if (!summary || item?.status !== "completed") return [];

  return [
    { label: "Total listens", value: Number(summary.derived_album_listens || 0).toLocaleString() },
    { label: "Total albums", value: Number(summary.final_album_count || 0).toLocaleString() },
    {
      label: "Average metadata lookup per album",
      value: summary.musicbrainz_lookup_seconds_avg
        ? `${Number(summary.musicbrainz_lookup_seconds_avg).toFixed(1)}s`
        : "N/A",
    },
    { label: "Found cached results", value: Number(summary.metadata_cache_hits || 0).toLocaleString() },
  ];
}

export function visibleImportStats(summary) {
  if (!summary) return [];
  return [
    { label: "Rows stored", value: summary.new_event_rows },
    { label: "Album listens", value: summary.derived_album_listens },
    { label: "Needs review", value: summary.review_candidates },
  ].filter((entry) => Number(entry.value || 0) > 0 || entry.label !== "Needs review");
}

export function formatImportDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function sourceLabel(source) {
  if (source === "lastfm" || source === "lastfm_import") return "Last.fm";
  if (source === "spotify_import" || source === "spotify_export_upload") return "Spotify ZIP";
  return source || "Import";
}
