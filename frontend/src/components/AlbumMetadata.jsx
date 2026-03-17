import AlbumInfoRow from "./AlbumInfoRow";

function AlbumMetadata({ album }) {
  return (
    <div className="space-y-3">
      <AlbumInfoRow
        label="Release"
        value={album.release_date}
        color="primary"
      />
      <AlbumInfoRow
        label="Label"
        value={album.label}
        color="muted"
      />
    </div>
  );
}

export default AlbumMetadata;