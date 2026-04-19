const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

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
  return requestJson("/album-state");
}

export async function refreshAlbumMetadata(albumId, payload = {}) {
  return requestJson(`/albums/${albumId}/refresh-metadata`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createAlbum(payload) {
  return requestJson("/albums", {
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
  return requestJson(`/albums/${albumId}/listens`, {
    method: "POST",
    body: JSON.stringify({ listened_at: listenedAt }),
  });
}

export async function mergeAlbum(albumId, targetAlbumId) {
  return requestJson(`/albums/${albumId}/merge`, {
    method: "POST",
    body: JSON.stringify({ target_album_id: targetAlbumId }),
  });
}

export async function deleteAlbum(albumId) {
  return requestJson(`/albums/${albumId}`, {
    method: "DELETE",
  });
}
