import AlbumActions from "./dataQuality/AlbumActions";
import AlbumEditForm from "./dataQuality/AlbumEditForm";

function DataQualityWriteTools({ selectedAlbum, onAlbumUpdated, onDataChanged }) {
  return (
    <div className="space-y-4">
      {selectedAlbum && (
        <section className="rounded-lg border border-border p-4">
          <div className="mb-4">
            <h2 className="text-sm font-semibold text-foreground">
              Selected album actions
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {selectedAlbum.artist} - {selectedAlbum.name}
            </p>
          </div>
          <AlbumActions
            album={selectedAlbum}
            onAlbumUpdated={onAlbumUpdated}
            onDataChanged={onDataChanged}
          />
          <AlbumEditForm
            album={selectedAlbum}
            onAlbumUpdated={onAlbumUpdated}
            onDataChanged={onDataChanged}
          />
        </section>
      )}
    </div>
  );
}

export default DataQualityWriteTools;
