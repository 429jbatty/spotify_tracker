import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { createAlbum } from "../services/albumApi";
import { Field, StatusMessage } from "./dataQuality/FormBits";
import { buildMetadataPayload, inputClass } from "./dataQuality/formUtils";

function AlbumCreateDialog({ onDataChanged, triggerClassName, variant = "default" }) {
  const initialForm = useMemo(
    () => ({
      artist: "",
      name: "",
      listen_date: "",
      release_year: "",
      release_month: "",
      release_day: "",
      label: "",
      image_url: "",
      spotify_url: "",
      musicbrainz_url: "",
    }),
    []
  );
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await createAlbum({
        ...buildMetadataPayload(form),
        listen_date: form.listen_date,
      });
      await onDataChanged?.();
      setForm(initialForm);
      setOpen(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={variant} size="sm" className={triggerClassName}>
          <Plus className="size-4" />
          Add Album
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add album</DialogTitle>
          <DialogDescription>
            Add an album and first listen date directly to the library.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Artist">
              <input
                className={inputClass}
                value={form.artist}
                onChange={(event) => updateField("artist", event.target.value)}
                required
              />
            </Field>
            <Field label="Album">
              <input
                className={inputClass}
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                required
              />
            </Field>
            <Field label="Listen date">
              <input
                className={inputClass}
                type="date"
                value={form.listen_date}
                onChange={(event) => updateField("listen_date", event.target.value)}
                required
              />
            </Field>
            <Field label="Release year">
              <input
                className={inputClass}
                inputMode="numeric"
                value={form.release_year}
                onChange={(event) => updateField("release_year", event.target.value)}
              />
            </Field>
            <Field label="Release month">
              <input
                className={inputClass}
                inputMode="numeric"
                value={form.release_month}
                onChange={(event) => updateField("release_month", event.target.value)}
              />
            </Field>
            <Field label="Release day">
              <input
                className={inputClass}
                inputMode="numeric"
                value={form.release_day}
                onChange={(event) => updateField("release_day", event.target.value)}
              />
            </Field>
          </div>

          <Field label="Label">
            <input
              className={inputClass}
              value={form.label}
              onChange={(event) => updateField("label", event.target.value)}
            />
          </Field>
          <Field label="Artwork URL">
            <input
              className={inputClass}
              value={form.image_url}
              onChange={(event) => updateField("image_url", event.target.value)}
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Spotify URL">
              <input
                className={inputClass}
                value={form.spotify_url}
                onChange={(event) => updateField("spotify_url", event.target.value)}
              />
            </Field>
            <Field label="MusicBrainz URL">
              <input
                className={inputClass}
                value={form.musicbrainz_url}
                onChange={(event) => updateField("musicbrainz_url", event.target.value)}
              />
            </Field>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Button type="submit" disabled={pending}>
              {pending ? "Adding..." : "Create album"}
            </Button>
            <StatusMessage error={error} />
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default AlbumCreateDialog;
