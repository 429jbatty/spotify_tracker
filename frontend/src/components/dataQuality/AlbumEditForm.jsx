import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { mergeAlbum, updateAlbum } from "../../services/albumApi";
import { Field, StatusMessage } from "./FormBits";
import AlbumListenEditor from "./AlbumListenEditor";
import {
  buildMetadataPayload,
  fieldValue,
  inputClass,
  textOrUndefined,
  validateImageUrl,
} from "./formUtils";

function AlbumEditForm({ album, onAlbumUpdated, onDataChanged }) {
  const [form, setForm] = useState({});
  const [pending, setPending] = useState(false);
  const [mergePending, setMergePending] = useState(false);
  const [mergeCandidate, setMergeCandidate] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    setForm({
      artist: fieldValue(album?.artist),
      name: fieldValue(album?.name),
      release_year: fieldValue(album?.release_year),
      release_month: fieldValue(album?.release_month),
      release_day: fieldValue(album?.release_day),
      label: fieldValue(album?.label),
      image_url: fieldValue(album?.remote_image_url || album?.image_url),
      spotify_url: fieldValue(album?.spotify_url),
      musicbrainz_url: fieldValue(album?.musicbrainz_url),
    });
    setMergeCandidate(null);
    setError(null);
    setMessage(null);
  }, [album]);

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const artworkUrlChanged = () => {
    const currentUrl = textOrUndefined(album?.remote_image_url || album?.image_url);
    const nextUrl = textOrUndefined(form.image_url);
    return currentUrl !== nextUrl;
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!album?.id) return;

    setPending(true);
    setError(null);
    setMessage(null);
    setMergeCandidate(null);
    try {
      if (textOrUndefined(form.image_url) && artworkUrlChanged()) {
        setMessage("Checking artwork URL...");
        const imageLoads = await validateImageUrl(form.image_url);
        if (!imageLoads) {
          setError("Artwork URL could not be loaded. Check the link or leave it blank.");
          setMessage(null);
          return;
        }
      }

      setMessage(null);
      const updated = await updateAlbum(album.id, buildMetadataPayload(form));
      onAlbumUpdated(updated);
      await onDataChanged?.();
      setMessage("Metadata saved.");
    } catch (err) {
      if (err.detail?.code === "duplicate_album_key" && err.detail.target_album) {
        setMergeCandidate(err.detail.target_album);
        setError(null);
        setMessage("This edit matches an existing album.");
      } else {
        setError(err.message);
      }
    } finally {
      setPending(false);
    }
  };

  const confirmMerge = async () => {
    if (!album?.id || !mergeCandidate?.id) return;

    setMergePending(true);
    setError(null);
    try {
      const updated = await mergeAlbum(album.id, mergeCandidate.id);
      onAlbumUpdated(updated);
      await onDataChanged?.();
      setMergeCandidate(null);
      setMessage("Albums merged.");
    } catch (err) {
      setError(err.message);
    } finally {
      setMergePending(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3 border-t border-border pt-4">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Edit metadata</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Save manual overrides for fields that the automatic lookup got wrong.
          A future metadata refresh can replace these values.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Artist">
          <input
            className={inputClass}
            value={form.artist || ""}
            onChange={(event) => updateField("artist", event.target.value)}
            required
          />
        </Field>
        <Field label="Album">
          <input
            className={inputClass}
            value={form.name || ""}
            onChange={(event) => updateField("name", event.target.value)}
            required
          />
        </Field>
        <Field label="Release year">
          <input
            className={inputClass}
            inputMode="numeric"
            value={form.release_year || ""}
            onChange={(event) => updateField("release_year", event.target.value)}
          />
        </Field>
        <Field label="Release month">
          <input
            className={inputClass}
            inputMode="numeric"
            value={form.release_month || ""}
            onChange={(event) => updateField("release_month", event.target.value)}
          />
        </Field>
        <Field label="Release day">
          <input
            className={inputClass}
            inputMode="numeric"
            value={form.release_day || ""}
            onChange={(event) => updateField("release_day", event.target.value)}
          />
        </Field>
        <Field label="Label">
          <input
            className={inputClass}
            value={form.label || ""}
            onChange={(event) => updateField("label", event.target.value)}
          />
        </Field>
      </div>

      <Field label="Artwork URL">
        <input
          className={inputClass}
          value={form.image_url || ""}
          onChange={(event) => updateField("image_url", event.target.value)}
        />
      </Field>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Spotify URL">
          <input
            className={inputClass}
            value={form.spotify_url || ""}
            onChange={(event) => updateField("spotify_url", event.target.value)}
          />
        </Field>
        <Field label="MusicBrainz URL">
          <input
            className={inputClass}
            value={form.musicbrainz_url || ""}
            onChange={(event) => updateField("musicbrainz_url", event.target.value)}
          />
        </Field>
      </div>

      <AlbumListenEditor
        album={album}
        onAlbumUpdated={onAlbumUpdated}
        onDataChanged={onDataChanged}
      />

      {mergeCandidate && (
        <div className="rounded-md border border-border/70 bg-muted/40 p-3 text-sm">
          <p className="font-medium text-foreground">
            Merge with existing album?
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {mergeCandidate.artist} - {mergeCandidate.name} already exists. Merge
            this album's listen history into that record and delete this duplicate.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              type="button"
              variant="destructive"
              disabled={mergePending}
              onClick={confirmMerge}
            >
              {mergePending ? "Merging..." : "Merge albums"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={mergePending}
              onClick={() => {
                setMergeCandidate(null);
                setMessage(null);
              }}
            >
              Keep separate
            </Button>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={pending || !album?.id}>
          {pending ? "Saving..." : "Save metadata"}
        </Button>
        <StatusMessage error={error} message={message} />
      </div>
    </form>
  );
}

export default AlbumEditForm;
