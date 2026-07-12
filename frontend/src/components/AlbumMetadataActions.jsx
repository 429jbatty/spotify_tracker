import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, DatabaseZap, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { refreshAlbumMetadata } from "../services/albumApi";
import AlbumEditForm from "./albumEditor/AlbumEditForm";
import { StatusMessage } from "./albumEditor/FormBits";
import AlbumDeleteDialog from "./AlbumDeleteDialog";

function valueKey(value) {
  if (Array.isArray(value)) return value.join("|");
  return String(value ?? "").trim();
}

function releaseDateKey(album) {
  return [
    album?.release_year || "",
    album?.release_month || "",
    album?.release_day || "",
  ].join("-");
}

function artworkKey(album) {
  return valueKey(album?.remote_image_url || album?.image_url);
}

function trackCreditCount(album) {
  return (album?.tracklist || []).reduce((count, track) => {
    return count + (Array.isArray(track.credits) ? track.credits.length : 0);
  }, 0);
}

function summarizeRefreshChanges(before, after) {
  const changes = [];

  if (valueKey(before?.artist) !== valueKey(after?.artist)) changes.push("artist");
  if (valueKey(before?.name) !== valueKey(after?.name)) changes.push("album title");
  if (releaseDateKey(before) !== releaseDateKey(after)) changes.push("release date");
  if (valueKey(before?.label) !== valueKey(after?.label)) changes.push("record label");
  if (artworkKey(before) !== artworkKey(after)) changes.push("cover art");
  if ((before?.tracklist || []).length !== (after?.tracklist || []).length) {
    changes.push("tracklist");
  }
  if (trackCreditCount(before) !== trackCreditCount(after)) {
    changes.push("track credits");
  }
  if (valueKey(before?.genres) !== valueKey(after?.genres)) changes.push("genres");
  if (valueKey(before?.tags) !== valueKey(after?.tags)) changes.push("tags");
  if (valueKey(before?.release_group_mbid) !== valueKey(after?.release_group_mbid)) {
    changes.push("MusicBrainz match");
  }

  if (changes.length === 0) {
    return "Metadata checked; no visible fields changed.";
  }

  return `Metadata refreshed: ${changes.join(", ")}.`;
}

function AlbumMetadataActions({
  album,
  onAlbumUpdated,
  onAlbumDeleted,
  onDataChanged,
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const hasWritableId = Boolean(album?.id);

  useEffect(() => {
    setOpen(false);
    setEditing(false);
    setPending(false);
    setError(null);
    setMessage(null);
  }, [album?.id]);

  const toggleOpen = () => {
    setOpen((current) => {
      if (current) setEditing(false);
      return !current;
    });
  };

  const refreshMetadata = async () => {
    if (!hasWritableId) return;

    setPending(true);
    setError(null);
    setMessage("Refreshing metadata...");
    try {
      const previousAlbum = album;
      const updated = await refreshAlbumMetadata(album.id);
      onAlbumUpdated?.(updated);
      await onDataChanged?.();
      setMessage(summarizeRefreshChanges(previousAlbum, updated));
    } catch (err) {
      setError(err.message);
      setMessage(null);
      setOpen(true);
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="border-t pt-4">
      <div className="space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              Metadata actions
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Pull fresh MusicBrainz metadata without opening edit tools.
            </p>
          </div>
          <Button
            type="button"
            disabled={!hasWritableId || pending}
            onClick={refreshMetadata}
            className="w-full sm:w-auto"
          >
            <DatabaseZap className="size-4" />
            {pending ? "Refreshing..." : "Refresh metadata"}
          </Button>
        </div>

        {(error || message) && <StatusMessage error={error} message={message} />}

        <button
          type="button"
          className="flex w-full items-center justify-between rounded-md border border-border/70 bg-muted/40 px-3 py-2 text-left text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-expanded={open}
          onClick={toggleOpen}
        >
          <span>Metadata tools</span>
          <span className="inline-flex items-center gap-1">
            {open ? "Hide edit/delete" : "Edit/delete"}
            {open ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
          </span>
        </button>
      </div>

      {open && (
        <div className="mt-3 flex flex-col gap-3 rounded-md border border-border/70 bg-background/70 p-3">
          <p className="text-xs text-muted-foreground">
            Edit is for deliberate overrides. Delete removes the album record and
            its listen history.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant={editing ? "secondary" : "ghost"}
              aria-expanded={editing}
              disabled={pending}
              onClick={() => setEditing((current) => !current)}
            >
              <Pencil className="size-4" />
              {editing ? "Close edit" : "Edit"}
            </Button>
            <AlbumDeleteDialog
              album={album}
              disabled={!hasWritableId || pending}
              onAlbumDeleted={onAlbumDeleted}
              onDataChanged={onDataChanged}
            />
          </div>
        </div>
      )}

      {open && editing && (
        <AlbumEditForm
          album={album}
          onAlbumUpdated={onAlbumUpdated}
          onDataChanged={onDataChanged}
        />
      )}
    </section>
  );
}

export default AlbumMetadataActions;
