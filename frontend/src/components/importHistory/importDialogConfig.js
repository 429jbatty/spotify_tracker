export const IMPORT_STATUS_LABELS = {
  queued: "Queued",
  fetching_lastfm: "Fetching Last.fm scrobbles",
  storing_scrobbles: "Storing new scrobbles",
  grouping_album_sessions: "Grouping album sessions",
  matching_cached_albums: "Matching cached albums",
  fetching_metadata: "Fetching MusicBrainz metadata",
  finalizing: "Finalizing import",
  completed: "Completed",
  failed: "Failed",
};

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
};

export function summaryCards(source, summary) {
  if (!summary) return [];
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

  const scrobbles = Number(summary.new_event_rows || 0).toLocaleString();
  const listens = Number(summary.derived_album_listens || 0).toLocaleString();
  const review = Number(summary.review_candidates || 0).toLocaleString();
  const pending = Number(summary.pending_metadata_candidates || 0).toLocaleString();

  if (["completed", "failed"].includes(status)) {
    const reviewText = summary.review_candidates
      ? ` ${review} unresolved album sessions need review.`
      : "";
    return `${scrobbles} scrobbles stored. ${listens} album listens created.${reviewText}`;
  }

  const pendingText = summary.pending_metadata_candidates
    ? ` ${pending} album sessions still need tracklists.`
    : "";
  return `${scrobbles} scrobbles stored so far. ${listens} album listens created so far.${pendingText}`;
}

export function progressPercent(summary) {
  const total = Number(summary?.progress_total || 0);
  const current = Number(summary?.progress_current || 0);
  if (!total || total <= 0) return null;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

export function progressText(summary, status) {
  const total = Number(summary?.progress_total || 0);
  const current = Number(summary?.progress_current || 0);
  const label = summary?.progress_label;
  if (status === "completed") return "Import complete";
  if (status === "failed") return "Import failed";
  if (!label || !total) return null;

  const currentText = current.toLocaleString();
  const totalText = total.toLocaleString();
  const lowerLabel = label.toLowerCase();

  if (lowerLabel.includes("last.fm")) {
    return `Fetched ${currentText} of ${totalText} Last.fm scrobbles`;
  }
  if (lowerLabel.includes("storing")) {
    return `Stored ${currentText} of ${totalText} scrobbles`;
  }
  if (lowerLabel.includes("cached")) {
    return `Checked ${currentText} of ${totalText} possible album sessions against saved tracklists`;
  }
  if (lowerLabel.includes("musicbrainz")) {
    return `Checked ${currentText} of ${totalText} unresolved album sessions with MusicBrainz`;
  }
  if (lowerLabel.includes("finalizing") || lowerLabel.includes("completed")) {
    return label;
  }

  return `${label}: ${currentText} of ${totalText}`;
}
