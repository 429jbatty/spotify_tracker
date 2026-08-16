import ResponsiveAlbumImage from "./ResponsiveAlbumImage";

function AlbumArtwork({ album }) {
  return (
    <div className="relative overflow-hidden aspect-square bg-card">
      <ResponsiveAlbumImage
        src={album.image_url}
        alt={album.name}
        sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 240px"
        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
      />
    </div>
  );
}

export default AlbumArtwork;
