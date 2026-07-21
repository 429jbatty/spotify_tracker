const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";
export const SELECTED_USER_STORAGE_KEY = "spotify_tracker_user_slug";

function joinUrl(baseUrl, path) {
  return `${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

async function requestJson(path, options = {}) {
  const response = await fetch(joinUrl(API_BASE_URL, path), {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    let detail = null;
    try {
      const payload = await response.json();
      detail = payload.detail;
      message =
        typeof payload.detail === "string"
          ? payload.detail
          : payload.detail?.message || message;
    } catch {
      // Keep the generic status message when the API does not return JSON.
    }
    const error = new Error(message);
    error.status = response.status;
    error.detail = detail;
    throw error;
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

async function requestForm(path, formData, options = {}) {
  const response = await fetch(joinUrl(API_BASE_URL, path), {
    ...options,
    body: formData,
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    let detail = null;
    try {
      const payload = await response.json();
      detail = payload.detail;
      message =
        typeof payload.detail === "string"
          ? payload.detail
          : payload.detail?.message || message;
    } catch {
      // Keep the generic status message when the API does not return JSON.
    }
    const error = new Error(message);
    error.status = response.status;
    error.detail = detail;
    throw error;
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export async function fetchAlbumState(userSlug = getSelectedUserSlug(), options = {}) {
  if (userSlug) return requestJson(`/users/${userSlug}/album-state`, options);
  return requestJson("/album-state", options);
}

export async function fetchUsers() {
  return requestJson("/users");
}

export async function createUser(payload) {
  return requestJson("/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchPublicRecentListens(limit = 5) {
  return requestJson(`/public/recent-listens?limit=${limit}`);
}

export async function fetchSplashData(options = {}) {
  return requestJson("/public/splash", options);
}

export async function fetchSpotifyStatus(userSlug = getSelectedUserSlug(), options = {}) {
  if (!userSlug) return { connected: false };
  return requestJson(`/users/${userSlug}/spotify/status`, options);
}

export async function fetchRecurringContributors(
  userSlug = getSelectedUserSlug(),
  { limit = 25, ...options } = {}
) {
  if (!userSlug) return null;
  return requestJson(`/users/${userSlug}/connections/recurring?limit=${limit}`, options);
}

export async function searchContributors(
  userSlug = getSelectedUserSlug(),
  { query = "", limit = 25, offset = 0, ...options } = {}
) {
  if (!userSlug) return null;
  const params = new URLSearchParams({
    query,
    limit: String(limit),
    offset: String(offset),
  });
  return requestJson(`/users/${userSlug}/connections/contributors?${params.toString()}`, options);
}

export async function fetchConnectionGraph(
  userSlug = getSelectedUserSlug(),
  {
    contributorLimit = 12,
    albumLimitPerContributor = 6,
    albumLimit = 48,
    focusNodeId = null,
    ...options
  } = {}
) {
  if (!userSlug) return null;
  const params = new URLSearchParams({
    contributor_limit: String(contributorLimit),
    album_limit_per_contributor: String(albumLimitPerContributor),
    album_limit: String(albumLimit),
  });
  if (focusNodeId) params.set("focus_node_id", focusNodeId);
  return requestJson(
    `/users/${userSlug}/connections/graph?${params.toString()}`,
    options
  );
}

export async function fetchAlbumCreditPairs(
  userSlug = getSelectedUserSlug(),
  { limit = 12, ...options } = {}
) {
  if (!userSlug) return null;
  return requestJson(`/users/${userSlug}/connections/album-pairs?limit=${limit}`, options);
}

export async function fetchAlbumConnectionGraph(
  userSlug = getSelectedUserSlug(),
  { albumAId, albumBId, ...options } = {}
) {
  if (!userSlug || !albumAId || !albumBId) return null;
  const params = new URLSearchParams({
    album_a_id: String(albumAId),
    album_b_id: String(albumBId),
  });
  return requestJson(
    `/users/${userSlug}/connections/album-connection?${params.toString()}`,
    options
  );
}

export async function fetchCreditPersonDetail(
  personKey,
  userSlug = getSelectedUserSlug(),
  options = {}
) {
  if (!userSlug || !personKey) return null;
  return requestJson(
    `/users/${userSlug}/connections/people/${encodeURIComponent(personKey)}`,
    options
  );
}

export function spotifyConnectUrl(userSlug = getSelectedUserSlug()) {
  if (!userSlug) return null;
  return joinUrl(API_BASE_URL, `/users/${userSlug}/spotify/connect`);
}

export async function syncSpotifyNow(userSlug = getSelectedUserSlug()) {
  return requestJson(`/users/${userSlug}/spotify/sync`, {
    method: "POST",
  });
}

export async function refreshAlbumMetadata(albumId, payload = {}) {
  return requestJson(`/albums/${albumId}/refresh-metadata`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createAlbum(payload) {
  const userSlug = getSelectedUserSlug();
  const path = userSlug ? `/users/${userSlug}/albums` : "/albums";
  return requestJson(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAlbum(albumId, payload) {
  return requestJson(`/albums/${albumId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function addAlbumListen(albumId, listenedAt) {
  const userSlug = getSelectedUserSlug();
  const path = userSlug
    ? `/users/${userSlug}/albums/${albumId}/listens`
    : `/albums/${albumId}/listens`;
  return requestJson(path, {
    method: "POST",
    body: JSON.stringify({ listened_at: listenedAt }),
  });
}

export async function deleteAlbumListen(albumId, listenedAt) {
  const userSlug = getSelectedUserSlug();
  const path = userSlug
    ? `/users/${userSlug}/albums/${albumId}/listens`
    : `/albums/${albumId}/listens`;
  return requestJson(path, {
    method: "DELETE",
    body: JSON.stringify({ listened_at: listenedAt }),
  });
}

export async function mergeAlbum(albumId, targetAlbumId) {
  return requestJson(`/albums/${albumId}/merge`, {
    method: "POST",
    body: JSON.stringify({ target_album_id: targetAlbumId }),
  });
}

export async function updateAlbumUserTags(albumId, yourTags) {
  const userSlug = getSelectedUserSlug();
  const path = userSlug
    ? `/users/${userSlug}/albums/${albumId}/your-tags`
    : `/albums/${albumId}/your-tags`;
  return requestJson(path, {
    method: "PUT",
    body: JSON.stringify({ your_tags: yourTags }),
  });
}

export async function updateAlbumUserFeedback(albumId, payload) {
  const userSlug = getSelectedUserSlug();
  const path = userSlug
    ? `/users/${userSlug}/albums/${albumId}/your-feedback`
    : `/albums/${albumId}/your-feedback`;
  return requestJson(path, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteAlbum(albumId) {
  return requestJson(`/albums/${albumId}`, {
    method: "DELETE",
  });
}

export async function previewImport(payload, userSlug = getSelectedUserSlug()) {
  if (!userSlug) throw new Error("Select a user before importing history.");
  return requestJson(`/users/${userSlug}/imports/preview`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function commitImport(payload, userSlug = getSelectedUserSlug()) {
  if (!userSlug) throw new Error("Select a user before importing history.");
  return requestJson(`/users/${userSlug}/imports/commit`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function uploadSpotifyImportZip(file, userSlug = getSelectedUserSlug()) {
  if (!userSlug) throw new Error("Select a user before importing history.");
  const formData = new FormData();
  formData.append("file", file);
  return requestForm(`/users/${userSlug}/imports/spotify/upload`, formData, {
    method: "POST",
  });
}

export async function fetchImportHistory(userSlug = getSelectedUserSlug()) {
  if (!userSlug) return [];
  return requestJson(`/users/${userSlug}/imports`);
}

export async function fetchImportReview(userSlug = getSelectedUserSlug()) {
  if (!userSlug) return [];
  return requestJson(`/users/${userSlug}/imports/review`);
}

export async function fetchImportLogs(
  importSessionId,
  userSlug = getSelectedUserSlug(),
  { limit = 100, order = "asc" } = {}
) {
  if (!userSlug || !importSessionId) return [];
  return requestJson(
    `/users/${userSlug}/imports/${importSessionId}/logs?limit=${limit}&order=${order}`
  );
}

export async function deleteImportSession(importSessionId, userSlug = getSelectedUserSlug()) {
  if (!userSlug) throw new Error("Select a user before deleting an import.");
  return requestJson(`/users/${userSlug}/imports/${importSessionId}`, {
    method: "DELETE",
  });
}

export async function resolveImportReview(reviewItemId, payload, userSlug = getSelectedUserSlug()) {
  if (!userSlug) throw new Error("Select a user before resolving imported rows.");
  return requestJson(`/users/${userSlug}/imports/review/${reviewItemId}/resolve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getSelectedUserSlug() {
  return window.localStorage.getItem(SELECTED_USER_STORAGE_KEY);
}

export function setSelectedUserSlug(userSlug) {
  if (userSlug) {
    window.localStorage.setItem(SELECTED_USER_STORAGE_KEY, userSlug);
  } else {
    window.localStorage.removeItem(SELECTED_USER_STORAGE_KEY);
  }
}
