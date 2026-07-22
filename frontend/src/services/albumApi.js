const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";
export const SELECTED_USER_STORAGE_KEY = "spotify_tracker_user_slug";
export const AUTH_SESSION_STORAGE_KEY = "spotify_tracker_auth_session";
export const OWNED_PROFILE_STORAGE_KEY = "spotify_tracker_owned_profiles";

function joinUrl(baseUrl, path) {
  return `${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

function authHeaders() {
  const token = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function storeAuthenticatedSession(payload) {
  if (payload?.session_token) {
    window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, payload.session_token);
  }
  window.localStorage.setItem(
    OWNED_PROFILE_STORAGE_KEY,
    JSON.stringify(payload?.profile_slugs || [payload?.slug].filter(Boolean))
  );
  return payload;
}

export function getOwnedProfileSlugs() {
  try {
    return JSON.parse(window.localStorage.getItem(OWNED_PROFILE_STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

async function requestJson(path, options = {}) {
  const { headers, ...requestOptions } = options;
  const response = await fetch(joinUrl(API_BASE_URL, path), {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(headers || {}),
    },
    ...requestOptions,
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
  const { headers, ...requestOptions } = options;
  const response = await fetch(joinUrl(API_BASE_URL, path), {
    headers: {
      ...authHeaders(),
      ...(headers || {}),
    },
    ...requestOptions,
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
  return storeAuthenticatedSession(await requestJson("/users", {
    method: "POST",
    body: JSON.stringify(payload),
  }));
}

export async function beginGoogleSignIn() {
  return requestJson("/auth/google/start");
}

export function storeGoogleSessionFromFragment(fragment = window.location.hash) {
  const params = new URLSearchParams(fragment.replace(/^#/, ""));
  const sessionToken = params.get("session_token");
  if (!sessionToken) throw new Error("Google sign-in did not return a session.");
  return storeAuthenticatedSession({
    session_token: sessionToken,
    profile_slugs: [],
  });
}

export async function fetchCurrentAccount() {
  return storeAuthenticatedSession(await requestJson("/auth/me"));
}

export function ownsProfile(userSlug) {
  return getOwnedProfileSlugs().includes(userSlug);
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

export async function spotifyConnectUrl(userSlug = getSelectedUserSlug()) {
  if (!userSlug) return null;
  const payload = await requestJson(`/users/${userSlug}/spotify/connect`, {
    method: "POST",
  });
  return payload.authorize_url;
}

export async function syncSpotifyNow(userSlug = getSelectedUserSlug()) {
  return requestJson(`/users/${userSlug}/spotify/sync`, {
    method: "POST",
  });
}

export async function disconnectSpotify(userSlug = getSelectedUserSlug()) {
  return requestJson(`/users/${userSlug}/spotify`, { method: "DELETE" });
}

export async function refreshAlbumMetadata(albumId, payload = {}) {
  const userSlug = getSelectedUserSlug();
  return requestJson(`/users/${userSlug}/albums/${albumId}/refresh-metadata`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createAlbum(payload) {
  const userSlug = getSelectedUserSlug();
  if (!userSlug) throw new Error("Sign in to add an album.");
  return requestJson(`/users/${userSlug}/albums`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAlbum(albumId, payload) {
  const userSlug = getSelectedUserSlug();
  return requestJson(`/users/${userSlug}/albums/${albumId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function addAlbumListen(albumId, listenedAt) {
  const userSlug = getSelectedUserSlug();
  if (!userSlug) throw new Error("Sign in to edit an album.");
  return requestJson(`/users/${userSlug}/albums/${albumId}/listens`, {
    method: "POST",
    body: JSON.stringify({ listened_at: listenedAt }),
  });
}

export async function deleteAlbumListen(albumId, listenedAt) {
  const userSlug = getSelectedUserSlug();
  if (!userSlug) throw new Error("Sign in to edit an album.");
  return requestJson(`/users/${userSlug}/albums/${albumId}/listens`, {
    method: "DELETE",
    body: JSON.stringify({ listened_at: listenedAt }),
  });
}

export async function mergeAlbum(albumId, targetAlbumId) {
  const userSlug = getSelectedUserSlug();
  return requestJson(`/users/${userSlug}/albums/${albumId}/merge`, {
    method: "POST",
    body: JSON.stringify({ target_album_id: targetAlbumId }),
  });
}

export async function updateAlbumUserTags(albumId, yourTags) {
  const userSlug = getSelectedUserSlug();
  if (!userSlug) throw new Error("Sign in to edit an album.");
  return requestJson(`/users/${userSlug}/albums/${albumId}/your-tags`, {
    method: "PUT",
    body: JSON.stringify({ your_tags: yourTags }),
  });
}

export async function updateAlbumUserFeedback(albumId, payload) {
  const userSlug = getSelectedUserSlug();
  if (!userSlug) throw new Error("Sign in to edit an album.");
  return requestJson(`/users/${userSlug}/albums/${albumId}/your-feedback`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteAlbum(albumId) {
  const userSlug = getSelectedUserSlug();
  return requestJson(`/users/${userSlug}/albums/${albumId}`, {
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
