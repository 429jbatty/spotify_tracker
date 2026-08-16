import { useEffect } from "react";

const SITE_NAME = "Albumary";

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
