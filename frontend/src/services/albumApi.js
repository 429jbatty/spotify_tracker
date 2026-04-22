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

export async function fetchAlbumState() {
  const userSlug = getSelectedUserSlug();
  if (userSlug) return requestJson(`/users/${userSlug}/album-state`);
  return requestJson("/album-state");
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

export async function fetchSpotifyStatus(userSlug = getSelectedUserSlug()) {
  if (!userSlug) return { connected: false };
  return requestJson(`/users/${userSlug}/spotify/status`);
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

export async function deleteAlbum(albumId) {
  return requestJson(`/albums/${albumId}`, {
    method: "DELETE",
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
