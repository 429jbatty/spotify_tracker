function AlbumArtwork({ album }) {
  const BASE = import.meta.env.BASE_URL;

  return (
    <div className="relative overflow-hidden aspect-square bg-card">
      <img
        loading="lazy"
        src={album.image_url || `${BASE}placeholder_art.png`}
        onError={(e) => {
          e.target.onerror = null;
          e.target.src = `${BASE}placeholder_art.png`;
        }}
        alt={album.name}
        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
      />
    </div>
  );
}

export default AlbumArtwork;