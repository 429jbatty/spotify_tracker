import { useState } from "react";
import { Button } from "@/components/ui/button";
import { addAlbumListen, refreshAlbumMetadata } from "../../services/albumApi";
import { inputClass, textOrUndefined } from "./formUtils";
import { StatusMessage } from "./FormBits";

function AlbumActions({ album, onAlbumUpdated, onDataChanged }) {
  const [spotifyUrl, setSpotifyUrl] = useState("");
  const [listenDate, setListenDate] = useState("");
  const [pendingAction, setPendingAction] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const hasWritableId = Boolean(album?.id);

  const runAction = async (action, successMessage) => {
    if (!hasWritableId) return;

    setPendingAction(action);
    setError(null);
    setMessage(null);
    try {
      const updated =
        action === "refresh"
          ? await refreshAlbumMetadata(album.id, {
              spotify_url: textOrUndefined(spotifyUrl),
            })
          : await addAlbumListen(album.id, listenDate);

      onAlbumUpdated(updated);
      await onDataChanged?.();
      setMessage(successMessage);
      if (action === "listen") setListenDate("");
    } catch (err) {
      setError(err.message);
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-foreground">Refresh metadata</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Pull current MusicBrainz metadata while keeping listen history.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto]">
          <input
            className={inputClass}
            placeholder="Optional Spotify URL"
            value={spotifyUrl}
            onChange={(event) => setSpotifyUrl(event.target.value)}
          />
          <Button
            type="button"
            disabled={!hasWritableId || pendingAction === "refresh"}
            onClick={() => runAction("refresh", "Metadata refreshed.")}
          >
            {pendingAction === "refresh" ? "Refreshing..." : "Refresh"}
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold text-foreground">Add listen</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Add a listen date without changing metadata.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto]">
          <input
            className={inputClass}
            type="date"
            value={listenDate}
            onChange={(event) => setListenDate(event.target.value)}
          />
          <Button
            type="button"
            disabled={!hasWritableId || !listenDate || pendingAction === "listen"}
            onClick={() => runAction("listen", "Listen added.")}
          >
            {pendingAction === "listen" ? "Adding..." : "Add listen"}
          </Button>
        </div>
      </div>

      <StatusMessage error={error} message={message} />
    </div>
  );
}

export default AlbumActions;
