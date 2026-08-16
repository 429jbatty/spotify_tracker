import { useEffect } from "react";

const SITE_NAME = "Albumary";

export function getProfileDocumentMetadata({
  profileName,
  viewName,
  path,
  album,
  albumMissing = false,
  hasError = false,
  profileMissing = false,
}) {
  if (hasError) {
    return {
      title: "Unable to load profile | Albumary",
      description: "Albumary could not load this profile.",
      path,
    };
  }

  if (profileMissing) {
    return {
      title: "Profile not found | Albumary",
      description: "The Albumary profile you requested is unavailable.",
      path,
    };
  }

  if (albumMissing) {
    return {
      title: "Album not found | Albumary",
      description: "The Albumary album you requested is unavailable.",
      path,
    };
  }

  if (album) {
    return {
      title: `${album.name} by ${album.artist} | ${profileName} | Albumary`,
      description: `View ${album.name} by ${album.artist} in ${profileName}'s Albumary listening history.`,
      path,
    };
  }

  return {
    title: `${profileName}'s ${viewName} | Albumary`,
    description: `Explore ${profileName}'s album listening history on Albumary.`,
    path,
  };
}

function upsertMeta(attribute, name, content) {
  let element = document.head.querySelector(`meta[${attribute}="${name}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attribute, name);
    document.head.appendChild(element);
  }
  element.setAttribute("content", content);
}

function upsertCanonical(url) {
  let element = document.head.querySelector('link[rel="canonical"]');
  if (!element) {
    element = document.createElement("link");
    element.setAttribute("rel", "canonical");
    document.head.appendChild(element);
  }
  element.setAttribute("href", url);
}

export function useDocumentMetadata({ title, description, path = window.location.pathname }) {
  useEffect(() => {
    const canonicalUrl = new URL(path, window.location.origin).href;
    document.title = title;
    upsertMeta("name", "description", description);
    upsertCanonical(canonicalUrl);
    upsertMeta("property", "og:title", title);
    upsertMeta("property", "og:description", description);
    upsertMeta("property", "og:url", canonicalUrl);
    upsertMeta("property", "og:type", "website");
    upsertMeta("property", "og:site_name", SITE_NAME);
  }, [description, path, title]);
}
