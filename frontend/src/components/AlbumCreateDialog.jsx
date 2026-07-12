import { useEffect, useMemo, useState } from "react";
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
import { addAlbumListen, createAlbum } from "../services/albumApi";
import { Field, StatusMessage } from "./albumEditor/FormBits";
import { inputClass, textOrUndefined } from "./albumEditor/formUtils";

const MODE_OPTIONS = [
  { id: "listen", label: "Log listen" },
  { id: "album", label: "New album" },
];

function normalize(value) {
  return String(value || "").toLowerCase().trim();
}

function formatDate(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function AlbumCreateDialog({
  albums = [],
  onDataChanged,
  triggerClassName,
  variant = "default",
}) {
  const initialForm = useMemo(
    () => ({
      artist: "",
      name: "",
      listen_date: "",
    }),
    []
  );
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("listen");
  const [form, setForm] = useState(initialForm);
  const [listenForm, setListenForm] = useState({
    query: "",
    listen_date: "",
  });
  const [selectedAlbumId, setSelectedAlbumId] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const sortedAlbums = useMemo(() => {
    return [...albums].sort((a, b) => {
      const aLatest = a.latestListen ? new Date(a.latestListen).getTime() : 0;
      const bLatest = b.latestListen ? new Date(b.latestListen).getTime() : 0;
      if (aLatest !== bLatest) return bLatest - aLatest;
      return `${a.artist} ${a.name}`.localeCompare(`${b.artist} ${b.name}`);
    });
  }, [albums]);

  const matchedAlbums = useMemo(() => {
    const query = normalize(listenForm.query);
    if (!query) return [];

    return sortedAlbums
      .filter((album) => {
        const haystack = normalize(`${album.artist} ${album.name}`);
        return haystack.includes(query);
      })
      .slice(0, 8);
  }, [listenForm.query, sortedAlbums]);

  const selectedAlbum = useMemo(() => {
    if (!selectedAlbumId) return null;
    return sortedAlbums.find((album) => String(album.id) === String(selectedAlbumId)) || null;
  }, [selectedAlbumId, sortedAlbums]);

  useEffect(() => {
    if (!selectedAlbumId) return;
    if (!sortedAlbums.some((album) => String(album.id) === String(selectedAlbumId))) {
      setSelectedAlbumId(null);
    }
  }, [selectedAlbumId, sortedAlbums]);

  const resetState = () => {
    setMode("listen");
    setForm(initialForm);
    setListenForm({
      query: "",
      listen_date: "",
    });
    setSelectedAlbumId(null);
    setPending(false);
    setError(null);
  };

  const handleOpenChange = (nextOpen) => {
    setOpen(nextOpen);
    if (!nextOpen) resetState();
  };

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const updateListenField = (field, value) => {
    setListenForm((current) => ({ ...current, [field]: value }));
  };

  const submitAlbum = async (event) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await createAlbum({
        artist: textOrUndefined(form.artist),
        name: textOrUndefined(form.name),
        listen_date: textOrUndefined(form.listen_date),
      });
      await onDataChanged?.();
      setOpen(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };

  const submitListen = async (event) => {
    event.preventDefault();
    if (!selectedAlbum || !listenForm.listen_date) return;

    setPending(true);
    setError(null);
    try {
      await addAlbumListen(selectedAlbum.id, listenForm.listen_date);
      await onDataChanged?.();
      setOpen(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant={variant} size="sm" className={triggerClassName}>
          <Plus className="size-4" />
          Add
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add or log</DialogTitle>
          <DialogDescription>
            Log a listen quickly or add a brand new album to the library.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2 rounded-md border border-border/70 bg-muted/30 p-1">
          {MODE_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => {
                setMode(option.id);
                setError(null);
              }}
              className={[
                "flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                mode === option.id
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              ].join(" ")}
            >
              {option.label}
            </button>
          ))}
        </div>

        {mode === "listen" ? (
          <form onSubmit={submitListen} className="space-y-4">
            {sortedAlbums.length === 0 ? (
              <div className="rounded-md border border-border/70 bg-muted/20 p-4 text-sm text-muted-foreground">
                You do not have any albums yet. Switch to <strong>New album</strong> to
                add your first one.
              </div>
            ) : (
              <>
                <Field label="Find album">
                  <input
                    className={inputClass}
                    value={listenForm.query}
                    onChange={(event) => updateListenField("query", event.target.value)}
                    placeholder="Search by artist or album"
                    autoFocus
                  />
                </Field>

                {selectedAlbum ? (
                  <div className="rounded-md border border-border/70 bg-muted/20 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-foreground">
                          {selectedAlbum.name}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {selectedAlbum.artist}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {selectedAlbum.totalListens || 0} listens
                          {selectedAlbum.latestListen
                            ? ` • last ${formatDate(selectedAlbum.latestListen)}`
                            : ""}
                        </p>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => setSelectedAlbumId(null)}
                      >
                        Change
                      </Button>
                    </div>
                  </div>
                ) : null}

                {!selectedAlbum && listenForm.query ? (
                  matchedAlbums.length > 0 ? (
                    <div className="rounded-md border border-border/70 bg-background/70">
                      {matchedAlbums.map((album) => (
                        <button
                          key={album.id}
                          type="button"
                          onClick={() => setSelectedAlbumId(album.id)}
                          className="flex w-full items-start justify-between gap-3 border-b border-border/70 px-3 py-3 text-left last:border-b-0 hover:bg-muted/40"
                        >
                          <div>
                            <p className="text-sm font-medium text-foreground">
                              {album.name}
                            </p>
                            <p className="text-sm text-muted-foreground">{album.artist}</p>
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {album.totalListens || 0} listens
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No albums matched that search.
                    </p>
                  )
                ) : null}

                <Field label="Listen date">
                  <input
                    className={inputClass}
                    type="date"
                    value={listenForm.listen_date}
                    onChange={(event) =>
                      updateListenField("listen_date", event.target.value)
                    }
                    required
                  />
                </Field>
              </>
            )}

            <div className="flex items-center gap-3 pt-2">
              <Button
                type="submit"
                disabled={pending || !selectedAlbum || !listenForm.listen_date}
              >
                {pending ? "Logging..." : "Log listen"}
              </Button>
              <StatusMessage error={error} />
            </div>
          </form>
        ) : (
          <form onSubmit={submitAlbum} className="space-y-3">
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
                />
              </Field>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <Button
                type="submit"
                disabled={
                  pending ||
                  !textOrUndefined(form.artist) ||
                  !textOrUndefined(form.name)
                }
              >
                {pending ? "Adding..." : "Create album"}
              </Button>
              <StatusMessage error={error} />
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default AlbumCreateDialog;
