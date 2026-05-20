export const inputClass =
  "h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary";

export function fieldValue(value) {
  return value ?? "";
}

export function numberOrUndefined(value) {
  if (value === "") return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function textOrUndefined(value) {
  const trimmed = String(value ?? "").trim();
  return trimmed ? trimmed : undefined;
}

export function buildMetadataPayload(form) {
  return {
    artist: textOrUndefined(form.artist),
    name: textOrUndefined(form.name),
    release_year: numberOrUndefined(form.release_year),
    release_month: numberOrUndefined(form.release_month),
    release_day: numberOrUndefined(form.release_day),
    label: fieldValue(form.label),
    image_url: fieldValue(form.image_url),
    spotify_url: textOrUndefined(form.spotify_url),
    musicbrainz_url: textOrUndefined(form.musicbrainz_url),
  };
}

export function validateImageUrl(url, timeoutMs = 8000) {
  const trimmed = textOrUndefined(url);
  if (!trimmed) return Promise.resolve(true);

  return new Promise((resolve) => {
    const image = new Image();
    const timeout = window.setTimeout(() => {
      cleanup();
      resolve(false);
    }, timeoutMs);

    const cleanup = () => {
      window.clearTimeout(timeout);
      image.onload = null;
      image.onerror = null;
    };

    image.onload = () => {
      cleanup();
      resolve(true);
    };
    image.onerror = () => {
      cleanup();
      resolve(false);
    };
    image.src = trimmed;
  });
}
