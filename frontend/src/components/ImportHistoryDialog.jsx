import { useCallback, useEffect, useMemo, useState } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  commitImport,
  deleteImportSession,
  fetchImportHistory,
  fetchImportReview,
  previewImport,
  resolveImportReview,
  uploadSpotifyImportZip,
} from "../services/albumApi";
import {
  ActiveImportStatus,
  ImportHistoryList,
  ImportSourcePanel,
  ReviewQueue,
} from "./importHistory/ImportHistorySections";

function ImportHistoryDialog({
  selectedUser,
  albums = [],
  onDataChanged,
  open,
  onOpenChange,
  triggerClassName,
  triggerVariant = "outline",
  hideTrigger = false,
}) {
  const [activeSource, setActiveSource] = useState("lastfm");
  const [lastfmUsername, setLastfmUsername] = useState("");
  const [spotifyFile, setSpotifyFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [history, setHistory] = useState([]);
  const [reviewItems, setReviewItems] = useState([]);
  const [expandedLogIds, setExpandedLogIds] = useState({});
  const [pendingPreview, setPendingPreview] = useState(false);
  const [pendingCommit, setPendingCommit] = useState(false);
  const [pendingResolveId, setPendingResolveId] = useState(null);
  const [pendingDeleteImportId, setPendingDeleteImportId] = useState(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState(null);
  const [resolveModeById, setResolveModeById] = useState({});
  const [existingSearchById, setExistingSearchById] = useState({});
  const [selectedExistingAlbumById, setSelectedExistingAlbumById] = useState({});
  const [createFormById, setCreateFormById] = useState({});

  const summary = preview?.summary;
  const selectedUserSlug = selectedUser?.slug;
  const canCommit = Boolean(summary && (summary.total_rows > 0 || summary.new_event_rows > 0));
  const activeImport = history.find((item) => !["completed", "failed"].includes(item.status));
  const activeImportId = activeImport?.id;
  const activeImportStatus = activeImport?.status;
  const normalizedAlbums = useMemo(
    () =>
      [...albums].sort((a, b) =>
        `${a.artist} ${a.name}`.localeCompare(`${b.artist} ${b.name}`)
      ),
    [albums]
  );

  const payload = useMemo(
    () => ({
      source: "lastfm",
      lastfm_username: lastfmUsername || null,
      session_name: lastfmUsername
        ? `Last.fm import for ${lastfmUsername.trim()} - ${new Date().toLocaleDateString()}`
        : null,
    }),
    [lastfmUsername]
  );

  const refreshImportData = useCallback(async () => {
    if (!selectedUserSlug) return { historyPayload: [], reviewPayload: [] };

    const [historyPayload, reviewPayload] = await Promise.all([
      fetchImportHistory(selectedUserSlug),
      fetchImportReview(selectedUserSlug),
    ]);
    setHistory(historyPayload);
    setReviewItems(reviewPayload);
    return { historyPayload, reviewPayload };
  }, [selectedUserSlug]);

  useEffect(() => {
    if (!open || !selectedUserSlug) return;

    setLoadingHistory(true);
    refreshImportData()
      .catch((err) => setError(err.message))
      .finally(() => setLoadingHistory(false));
  }, [open, refreshImportData, selectedUserSlug]);

  useEffect(() => {
    if (!open || !selectedUserSlug || (!pendingCommit && !activeImportId)) return undefined;

    const refresh = () => {
      fetchImportHistory(selectedUserSlug)
        .then((historyPayload) => {
          setHistory(historyPayload);
          const nextActiveImport = historyPayload.find(
            (item) => !["completed", "failed"].includes(item.status)
          );
          if (nextActiveImport) {
            onDataChanged?.();
          }
          if (activeImportId && !nextActiveImport) {
            return Promise.all([
              fetchImportReview(selectedUserSlug).then((reviewPayload) =>
                setReviewItems(reviewPayload)
              ),
              onDataChanged?.(),
            ]);
          }
          return null;
        })
        .catch((err) => setError(err.message));
    };
    refresh();
    const intervalId = window.setInterval(refresh, 2000);
    return () => window.clearInterval(intervalId);
  }, [
    activeImportId,
    activeImportStatus,
    onDataChanged,
    open,
    pendingCommit,
    selectedUserSlug,
  ]);

  const resetState = () => {
    setActiveSource("lastfm");
    setLastfmUsername("");
    setSpotifyFile(null);
    setPreview(null);
    setHistory([]);
    setReviewItems([]);
    setExpandedLogIds({});
    setError(null);
  };

  const handleDialogChange = (nextOpen) => {
    onOpenChange?.(nextOpen);
    if (!nextOpen) resetState();
  };

  const handlePreview = async () => {
    setPendingPreview(true);
    setError(null);
    try {
      const nextPreview = await previewImport(payload, selectedUserSlug);
      setPreview(nextPreview);
    } catch (err) {
      setError(err.message);
    } finally {
      setPendingPreview(false);
    }
  };

  const handleSpotifyUpload = async () => {
    if (!spotifyFile) {
      setError("Choose a Spotify ZIP file first.");
      return;
    }
    setPendingCommit(true);
    setError(null);
    try {
      await uploadSpotifyImportZip(spotifyFile, selectedUserSlug);
      const { historyPayload } = await refreshImportData();
      const nextActiveImport = historyPayload.find(
        (item) => !["completed", "failed"].includes(item.status)
      );
      if (!nextActiveImport) {
        await onDataChanged?.();
      }
      setSpotifyFile(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setPendingCommit(false);
    }
  };

  const handleCommit = async () => {
    setPendingCommit(true);
    setError(null);
    try {
      await commitImport(payload, selectedUserSlug);
      const { historyPayload } = await refreshImportData();
      const nextActiveImport = historyPayload.find(
        (item) => !["completed", "failed"].includes(item.status)
      );
      if (!nextActiveImport) {
        await onDataChanged?.();
      }
      setPreview(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setPendingCommit(false);
    }
  };

  const resolveMode = (itemId) => resolveModeById[itemId] || "existing";
  const createForm = (item) =>
    createFormById[item.id] || {
      artist: item.artist || "",
      name: item.album || "",
      listened_at: item.listened_at || "",
    };
  const existingMatches = (itemId) => {
    const query = String(existingSearchById[itemId] || "").trim().toLowerCase();
    if (!query) return [];
    return normalizedAlbums
      .filter((album) =>
        `${album.artist} ${album.name}`.toLowerCase().includes(query)
      )
      .slice(0, 8);
  };

  const refreshReviewData = async () => {
    await Promise.all([refreshImportData(), onDataChanged?.()]);
  };

  const handleDeleteImport = async (item) => {
    const label = item.session_name || item.source || "this import";
    const confirmed = window.confirm(
      `Delete "${label}"? This removes the stored import rows and any album listens that were created from this import.`
    );
    if (!confirmed) return;

    setPendingDeleteImportId(item.id);
    setError(null);
    try {
      await deleteImportSession(item.id, selectedUserSlug);
      await refreshReviewData();
    } catch (err) {
      setError(err.message);
    } finally {
      setPendingDeleteImportId(null);
    }
  };

  const toggleImportAdvanced = (itemId) => {
    const nextExpanded = !expandedLogIds[itemId];
    setExpandedLogIds((current) => ({ ...current, [itemId]: nextExpanded }));
  };

  const handleResolve = async (item) => {
    setPendingResolveId(item.id);
    setError(null);
    try {
      if (resolveMode(item.id) === "existing") {
        const selected = normalizedAlbums.find(
          (album) => String(album.id) === String(selectedExistingAlbumById[item.id])
        );
        if (!selected?.id) throw new Error("Pick or search for an album to match.");
        await resolveImportReview(
          item.id,
          { existing_album_id: selected.id },
          selectedUserSlug
        );
      } else {
        const form = createForm(item);
        if (!form.artist || !form.name || !form.listened_at) {
          throw new Error("Artist, album, and listened at are required.");
        }
        await resolveImportReview(
          item.id,
          { create_album: form },
          selectedUserSlug
        );
      }
      await refreshReviewData();
    } catch (err) {
      setError(err.message);
    } finally {
      setPendingResolveId(null);
    }
  };

  const updateCreateForm = (itemId, field, value) => {
    setCreateFormById((current) => ({
      ...current,
      [itemId]: {
        ...(current[itemId] || {}),
        [field]: value,
      },
    }));
  };

  const refreshHistory = () => {
    setLoadingHistory(true);
    refreshImportData()
      .catch((err) => setError(err.message))
      .finally(() => setLoadingHistory(false));
  };

  return (
    <Dialog open={open} onOpenChange={handleDialogChange}>
      {!hideTrigger && (
        <DialogTrigger asChild>
          <Button variant={triggerVariant} className={triggerClassName}>
            <Upload className="size-4" />
            Import History
          </Button>
        </DialogTrigger>
      )}
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Import listening history</DialogTitle>
          <DialogDescription>
            Add Last.fm or Spotify listening history for {selectedUser?.display_name}.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-5">
          <ImportSourcePanel
            activeSource={activeSource}
            setActiveSource={setActiveSource}
            lastfmUsername={lastfmUsername}
            setLastfmUsername={setLastfmUsername}
            spotifyFile={spotifyFile}
            setSpotifyFile={setSpotifyFile}
            preview={preview}
            summary={summary}
            error={error}
            pendingPreview={pendingPreview}
            pendingCommit={pendingCommit}
            canCommit={canCommit}
            onPreview={handlePreview}
            onCommit={handleCommit}
            onSpotifyUpload={handleSpotifyUpload}
            onClearPreview={() => setPreview(null)}
            onClearError={() => setError(null)}
          />

          <ActiveImportStatus activeImport={activeImport} pendingCommit={pendingCommit} />

          <ImportHistoryList
            history={history}
            loadingHistory={loadingHistory}
            pendingDeleteImportId={pendingDeleteImportId}
            expandedLogIds={expandedLogIds}
            onRefresh={refreshHistory}
            onDelete={handleDeleteImport}
            onToggleAdvanced={toggleImportAdvanced}
          />

          <ReviewQueue
            reviewItems={reviewItems}
            resolveMode={resolveMode}
            setResolveModeById={setResolveModeById}
            existingSearchById={existingSearchById}
            setExistingSearchById={setExistingSearchById}
            selectedExistingAlbumById={selectedExistingAlbumById}
            setSelectedExistingAlbumById={setSelectedExistingAlbumById}
            existingMatches={existingMatches}
            createForm={createForm}
            updateCreateForm={updateCreateForm}
            pendingResolveId={pendingResolveId}
            onResolve={handleResolve}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default ImportHistoryDialog;
