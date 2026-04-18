import AlbumBubble from "./AlbumBubble";

function AlbumCluster({ albums, onAlbumClick }) {
  return (
    <div className="mt-6 flex flex-wrap justify-center gap-4 max-w-xl">
      {albums.map((album) => (
        <AlbumBubble
          key={album.id || album.release_group_mbid}
          album={album}
          onClick={() => onAlbumClick?.(album)}
        />
      ))}
    </div>
  );
}

export default AlbumCluster;
