const LOCAL_ARTWORK_PATTERN = /^(.*-sha256-[0-9a-f]{12})(\.[^./?]+)(?:\?.*)?$/;
const VARIANT_WIDTHS = [240, 640];

export function artworkSourceSet(src) {
  if (!src || !src.startsWith("/media/artwork/")) return undefined;

  const match = src.match(LOCAL_ARTWORK_PATTERN);
  if (!match) return undefined;

  return VARIANT_WIDTHS.map((width) => `${match[1]}-${width}.webp ${width}w`).join(", ");
}

export function artworkVariantUrl(src, width = 240) {
  const srcSet = artworkSourceSet(src);
  if (!srcSet) return src;

  const candidate = srcSet
    .split(", ")
    .find((entry) => entry.endsWith(` ${width}w`));
  return candidate?.split(" ")[0] || src;
}
