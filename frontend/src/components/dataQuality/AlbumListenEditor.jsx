import { useState } from "react";
import { Button } from "@/components/ui/button";
import { addAlbumListen, deleteAlbumListen } from "../../services/albumApi";
import { inputClass } from "./formUtils";
import { StatusMessage } from "./FormBits";

function formatListenDate(value) {
  if (!value) return "Unknown";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function AlbumListenEditor({ album, onAlbumUpdated, onDataChanged }) {
  const [listenDate, setListenDate] = useState("");
  const [pendingAction, setPendingAction] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const listens = [...(album?.listen_history || [])].reverse();
  const hasWritableId = Boolean(album?.id);

  const handleAddListen = async () => {
    if (!hasWritableId || !listenDate) return;

    setPendingAction("add");
    setError(null);
    setMessage(null);
    try {
      const updated = await addAlbumListen(album.id, listenDate);
      onAlbumUpdated(updated);
      await onDataChanged?.();
      setListenDate("");
      setMessage("Listen added.");
    } catch (err) {
      setError(err.message);
    } finally {
      setPendingAction(null);
    }
  };

  const handleDeleteListen = async (listenedAt) => {
    if (!hasWritableId || !listenedAt) return;

    setPendingAction(listenedAt);
    setError(null);
    setMessage(null);
    try {
      const updated = await deleteAlbumListen(album.id, listenedAt);
      onAlbumUpdated(updated);
      await onDataChanged?.();
      setMessage("Listen removed.");
    } catch (err) {
      setError(err.message);
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <section className="space-y-3 rounded-md border border-border/70 bg-muted/20 p-3">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Listens</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Add a new listen or remove one that was logged by mistake.
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <input
          className={inputClass}
          type="date"
          value={listenDate}
          onChange={(event) => setListenDate(event.target.value)}
        />
        <Button
          type="button"
          variant="outline"
          disabled={!hasWritableId || !listenDate || pendingAction === "add"}
          onClick={handleAddListen}
        >
          {pendingAction === "add" ? "Adding..." : "Add listen"}
        </Button>
      </div>

      {listens.length > 0 ? (
        <div className="divide-y divide-border/70 rounded-md border border-border/70 bg-background/70">
          {listens.map((listenedAt, index) => (
            <div
              key={`${listenedAt}-${index}`}
              className="flex items-center justify-between gap-3 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="text-sm text-foreground">{formatListenDate(listenedAt)}</p>
                <p className="truncate text-xs text-muted-foreground">{listenedAt}</p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={pendingAction === listenedAt}
                onClick={() => handleDeleteListen(listenedAt)}
              >
                {pendingAction === listenedAt ? "Removing..." : "Remove"}
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No listens logged.</p>
      )}

      <StatusMessage error={error} message={message} />
    </section>
  );
}

export default AlbumListenEditor;
