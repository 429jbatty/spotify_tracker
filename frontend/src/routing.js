export const PROFILE_ROUTES = {
  discovery: "discovery",
  library: "library",
  releases: "releases",
  quality: "quality",
};

export const LEGACY_PROFILE_ROUTES = {
  albums: PROFILE_ROUTES.library,
  timeline: PROFILE_ROUTES.releases,
};

export function profilePath(userSlug, section = PROFILE_ROUTES.discovery) {
  return `/${userSlug}/${section}`;
}

export function albumPath(userSlug, albumId) {
  return `/${userSlug}/albums/${albumId}`;
}

export function getActiveView(pathname) {
  const segments = pathname.split("/").filter(Boolean);
  const section = segments[1];
  if (segments[1] === "albums" && segments[2]) return PROFILE_ROUTES.library;
  if (Object.values(PROFILE_ROUTES).includes(section)) return section;
  if (LEGACY_PROFILE_ROUTES[section]) return LEGACY_PROFILE_ROUTES[section];
  return PROFILE_ROUTES.discovery;
}

export function legacyRedirectPath(userSlug, legacySection) {
  const nextSection = LEGACY_PROFILE_ROUTES[legacySection];
  return nextSection ? profilePath(userSlug, nextSection) : null;
}

export function parseLibrarySortParam(sortParam) {
  if (sortParam === "recent" || !sortParam) {
    return { sortBy: "latestListen", ascending: false };
  }
  if (sortParam === "oldest") {
    return { sortBy: "latestListen", ascending: true };
  }

  const [sortBy, direction] = sortParam.split(":");
  if (!sortBy) return { sortBy: "latestListen", ascending: false };
  return { sortBy, ascending: direction === "asc" };
}

export function formatLibrarySortParam(sortBy, ascending) {
  if (sortBy === "latestListen") return ascending ? "oldest" : "recent";
  return `${sortBy}:${ascending ? "asc" : "desc"}`;
}

export function normalizeDiscoveryRange(rangeParam, allowedRanges) {
  return allowedRanges.includes(rangeParam) ? rangeParam : "1y";
}
