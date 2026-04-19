const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

function joinUrl(baseUrl, path) {
  return `${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

export async function fetchAlbumState() {
  const response = await fetch(joinUrl(API_BASE_URL, "/album-state"));

  if (!response.ok) {
    throw new Error("Failed to fetch album data");
  }

  return response.json();
}
