import AlbumBubble from "./AlbumBubble";

function AlbumCluster({ albums }) {
  return (
    <div className="mt-6 flex flex-wrap justify-center gap-4 max-w-xl">
      {albums.map((album) => (
        <AlbumBubble key={album.release_group_mbid} album={album} />
      ))}
    </div>
  );
}

export default AlbumCluster;