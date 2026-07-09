export const ROLE_LABELS = {
  producer: "Producer",
  writer_composer: "Writer",
  mixing_mastering: "Mixing/mastering",
  engineering: "Engineering",
  performer: "Performer",
  primary_artist: "Primary artist",
  other: "Other",
};

export const QUALITY_LABELS = {
  high_credit_album: "High-credit album",
  legacy_credit: "Legacy credit",
  low_track_share: "Low track share",
  name_only_identity: "Name-only identity",
  single_track_credit: "Single-track credit",
  enriched_credit: "Enriched credit",
  unresolved_identity: "Unresolved identity",
  generic_instrument: "Generic instrument",
  primary_artist_candidate: "Primary artist candidate",
};

export function formatCount(count, singular, plural = `${singular}s`) {
  return `${count.toLocaleString()} ${count === 1 ? singular : plural}`;
}

export function formatPercent(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

export function formatRoleLabel(role) {
  return ROLE_LABELS[role] || role.replaceAll("_", " ");
}

export function formatQualityLabel(flag) {
  return QUALITY_LABELS[flag] || flag.replaceAll("_", " ");
}

export function formatRoleSummary(roleBuckets = {}) {
  return Object.entries(roleBuckets)
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([role, count]) => `${formatRoleLabel(role)} ${count}`)
    .join(", ");
}

export function getPrimaryRole(roleBuckets = {}) {
  const [role] = Object.entries(roleBuckets).sort(
    (left, right) => right[1] - left[1] || left[0].localeCompare(right[0])
  )[0] || ["other"];
  return role;
}
