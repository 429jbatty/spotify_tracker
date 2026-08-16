import { artworkSourceSet } from "@/lib/artworkSources";

function ResponsiveAlbumImage({
  src,
  alt,
  className,
  sizes = "(max-width: 640px) 50vw, 240px",
  loading = "lazy",
  hideOnError = false,
}) {
  const fallbackImage = `${import.meta.env.BASE_URL}placeholder_art.png`;
  const resolvedSrc = src || fallbackImage;
  const srcSet = artworkSourceSet(resolvedSrc);

  return (
    <img
      src={resolvedSrc}
      srcSet={srcSet}
      sizes={srcSet ? sizes : undefined}
      alt={alt}
      className={className}
      loading={loading}
      decoding="async"
      onError={(event) => {
        const image = event.currentTarget;
        if (image.hasAttribute("srcset")) {
          image.removeAttribute("srcset");
          image.removeAttribute("sizes");
          image.src = resolvedSrc;
          return;
        }

        if (hideOnError) {
          image.style.display = "none";
        } else if (image.getAttribute("src") === fallbackImage) {
          image.style.display = "none";
        } else {
          image.src = fallbackImage;
        }
      }}
    />
  );
}

export default ResponsiveAlbumImage;
