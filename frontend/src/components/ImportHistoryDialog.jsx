import { useCallback, useEffect, useMemo, useState } from "react";
import { FileArchive, Upload, History, RefreshCcw, Trash2 } from "lucide-react";
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
  IMPORT_STATUS_LABELS,
  importSummaryText,
  progressPercent,
  progressText,
  previewSummaryNote,
  summaryCards,
} from "./importHistory/importDialogConfig";
import {
  SourceGuide,
  SummaryStat,
} from "./importHistory/ImportDialogFields";

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
  const hasPreviewRows = (preview?.rows || []).length > 0;
  const canCommit = Boolean(summary && (summary.total_rows > 0 || summary.new_event_rows > 0));
  const activeImport = history.find((item) => !["completed", "failed"].includes(item.status));
  const activeImportId = activeImport?.id;
  const activeImportStatus = activeImport?.status;
  const showImportStatus = pendingCommit || Boolean(activeImport);
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
  }, [activeImportId, activeImportStatus, onDataChanged, open, pendingCommit, selectedUserSlug]);

  const resetState = () => {
    setActiveSource("lastfm");
    setLastfmUsername("");
    setSpotifyFile(null);
    setPreview(null);
    setHistory([]);
    setReviewItems([]);
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
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Import listening history</DialogTitle>
          <DialogDescription>
            Import Last.fm or Spotify history into {selectedUser?.display_name}.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-5">
            <div className="space-y-4 rounded-2xl border border-border/70 bg-card p-5">
              <div className="grid grid-cols-2 gap-2 rounded-md border border-border/70 bg-background/70 p-1">
                {[
                  ["lastfm", "Last.fm"],
                  ["spotify_import", "Spotify ZIP"],
                ].map(([source, label]) => (
                  <button
                    key={source}
                    type="button"
                    onClick={() => {
                      setActiveSource(source);
                      setPreview(null);
                      setError(null);
                    }}
                    className={[
                      "rounded-md px-3 py-2 text-sm font-medium",
                      activeSource === source
                        ? "bg-foreground text-background"
                        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                    ].join(" ")}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <SourceGuide source={activeSource} />

              {activeSource === "lastfm" ? (
                <>
                  <label className="space-y-1">
                    <span className="text-xs font-medium text-muted-foreground">Last.fm username</span>
                    <input
                      value={lastfmUsername}
                      onChange={(event) => setLastfmUsername(event.target.value)}
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                      placeholder="your-lastfm-name"
                    />
                  </label>

                  <div className="flex flex-wrap items-center gap-3">
                    <Button type="button" onClick={handlePreview} disabled={pendingPreview}>
                      {pendingPreview ? "Previewing..." : "Preview Import"}
                    </Button>
                    {preview && (
                      <Button type="button" variant="outline" onClick={handleCommit} disabled={!canCommit || pendingCommit}>
                        {pendingCommit ? "Starting..." : "Start Background Import"}
                      </Button>
                    )}
                    {error && <p className="text-sm text-destructive">{error}</p>}
                  </div>
                </>
              ) : (
                <div className="space-y-3">
                  <label
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      event.preventDefault();
                      const file = event.dataTransfer.files?.[0];
                      if (file) setSpotifyFile(file);
                    }}
                    className="flex min-h-36 cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-background/70 p-5 text-center hover:bg-muted/30"
                  >
                    <FileArchive className="size-8 text-muted-foreground" />
                    <span className="text-sm font-medium text-foreground">
                      {spotifyFile ? spotifyFile.name : "Drop Spotify ZIP here"}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      Or choose the Extended Streaming History ZIP from Spotify.
                    </span>
                    <input
                      type="file"
                      accept=".zip,application/zip"
                      className="sr-only"
                      onChange={(event) => setSpotifyFile(event.target.files?.[0] || null)}
                    />
                  </label>
                  <div className="flex flex-wrap items-center gap-3">
                    <Button
                      type="button"
                      onClick={handleSpotifyUpload}
                      disabled={!spotifyFile || pendingCommit}
                    >
                      {pendingCommit ? "Uploading..." : "Upload and Start Import"}
                    </Button>
                    {error && <p className="text-sm text-destructive">{error}</p>}
                  </div>
                </div>
              )}
              {showImportStatus && (
                <div className="rounded-xl border border-border/70 bg-muted/30 p-3 text-sm">
                  <p className="font-medium text-foreground">
                    {activeImport
                      ? IMPORT_STATUS_LABELS[activeImport.status] || activeImport.status
                      : "Starting import..."}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    You can leave this dialog open while Albumary updates the import history below.
                    Large imports store source events first, then match albums from local or
                    cached tracklists before fetching MusicBrainz metadata in the background.
                  </p>
                </div>
              )}
            </div>

            {summary && (
              <div className="space-y-4 rounded-2xl border border-border/70 bg-card p-5">
                <div className="grid gap-3 sm:grid-cols-2">
                  {summaryCards(activeSource, summary).map((card) => (
                    <SummaryStat key={card.label} label={card.label} value={card.value} />
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  {previewSummaryNote(summary)}
                </p>

                {hasPreviewRows && (
                  <div className="overflow-hidden rounded-xl border border-border/70">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/40 text-left">
                        <tr>
                          <th className="px-3 py-2 font-medium">Artist</th>
                          <th className="px-3 py-2 font-medium">Album</th>
                          <th className="px-3 py-2 font-medium">When</th>
                          <th className="px-3 py-2 font-medium">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.rows.map((row, index) => (
                          <tr key={`${row.listened_at}-${row.artist}-${index}`} className="border-t border-border/70">
                            <td className="px-3 py-2">{row.artist || "Unknown artist"}</td>
                            <td className="px-3 py-2">{row.album || row.track || "Missing album"}</td>
                            <td className="px-3 py-2 text-muted-foreground">{row.listened_at || "Missing date"}</td>
                            <td className="px-3 py-2">
                              <div className="font-medium text-foreground">{row.status}</div>
                              {row.status_detail && (
                                <div className="text-xs text-muted-foreground">{row.status_detail}</div>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="space-y-5">
            <div className="rounded-2xl border border-border/70 bg-card p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-foreground">Import history</p>
                  <p className="text-xs text-muted-foreground">
                    Previous import runs. Deleting one removes its stored rows and matched listens.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setLoadingHistory(true);
                    refreshImportData()
                      .catch((err) => setError(err.message))
                      .finally(() => setLoadingHistory(false));
                  }}
                >
                  <RefreshCcw className="size-4" />
                </Button>
              </div>

              {loadingHistory ? (
                <p className="mt-4 text-sm text-muted-foreground">Loading import history...</p>
              ) : history.length > 0 ? (
                <div className="mt-4 space-y-3">
                  {history.map((item) => (
                    <div key={item.id} className="rounded-xl border border-border/70 bg-background/70 p-3">
                      {(() => {
                        const percent = progressPercent(item.summary);
                        const label = progressText(item.summary, item.status);
                        const isActive = !["completed", "failed"].includes(item.status);
                        return (
                          <>
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-foreground">
                            {item.session_name || item.source}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {item.source}
                            {item.source_user_id ? ` • ${item.source_user_id}` : ""}
                          </p>
                          <p className="mt-1 text-xs font-medium text-foreground">
                            {IMPORT_STATUS_LABELS[item.status] || item.status}
                          </p>
                        </div>
                        <div className="flex items-start gap-2">
                          <div className="flex items-center gap-2 pt-2 text-xs text-muted-foreground">
                            <History className="size-3.5" />
                            {item.started_at}
                          </div>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="size-8 text-muted-foreground hover:text-destructive"
                            disabled={pendingDeleteImportId === item.id}
                            onClick={() => handleDeleteImport(item)}
                            aria-label={`Delete import ${item.session_name || item.source}`}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">
                        {importSummaryText(item.summary, item.status)}
                      </p>
                      {isActive && percent !== null ? (
                        <div className="mt-3 space-y-1.5">
                          <div className="h-2 overflow-hidden rounded-full bg-muted">
                            <div
                              className="h-full rounded-full bg-foreground transition-all"
                              style={{ width: `${percent}%` }}
                            />
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {label} • {percent}%
                          </p>
                        </div>
                      ) : label ? (
                        <p className="mt-3 rounded-md bg-muted/50 px-2.5 py-1.5 text-xs text-muted-foreground">
                          {label}
                        </p>
                      ) : null}
                          </>
                        );
                      })()}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-4 text-sm text-muted-foreground">No imports yet.</p>
              )}
            </div>

            <div className="rounded-2xl border border-border/70 bg-card p-5">
              <p className="text-sm font-medium text-foreground">Unresolved album sessions</p>
              <p className="text-xs text-muted-foreground">
                Imported sessions that might be album listens but could not be matched automatically. Match one to an existing album or create an album when you are confident it belongs in your album history.
              </p>

              {reviewItems.length > 0 ? (
                <div className="mt-4 space-y-3">
                  {reviewItems.map((item) => (
                    <div key={item.id} className="rounded-xl border border-border/70 bg-background/70 p-3">
                      <p className="text-sm font-medium text-foreground">
                        {item.artist}
                        {item.album ? ` - ${item.album}` : item.track ? ` - ${item.track}` : ""}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {item.listened_at} • {item.source}
                        {item.source_user_id ? ` • ${item.source_user_id}` : ""}
                      </p>
                      {item.status_detail && (
                        <p className="mt-2 text-xs text-destructive">{item.status_detail}</p>
                      )}
                      <div className="mt-3 space-y-3 border-t border-border/70 pt-3">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              setResolveModeById((current) => ({
                                ...current,
                                [item.id]: "existing",
                              }))
                            }
                            className={[
                              "rounded-md px-2 py-1 text-xs",
                              resolveMode(item.id) === "existing"
                                ? "bg-foreground text-background"
                                : "border border-border text-muted-foreground",
                            ].join(" ")}
                          >
                            Match existing
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setResolveModeById((current) => ({
                                ...current,
                                [item.id]: "create",
                              }))
                            }
                            className={[
                              "rounded-md px-2 py-1 text-xs",
                              resolveMode(item.id) === "create"
                                ? "bg-foreground text-background"
                                : "border border-border text-muted-foreground",
                            ].join(" ")}
                          >
                            Create album
                          </button>
                        </div>

                        {resolveMode(item.id) === "existing" ? (
                          <div className="space-y-2">
                            <input
                              value={existingSearchById[item.id] || ""}
                              onChange={(event) =>
                                setExistingSearchById((current) => ({
                                  ...current,
                                  [item.id]: event.target.value,
                                }))
                              }
                              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                              placeholder="Search existing albums"
                            />
                            {existingSearchById[item.id]?.trim() && (
                              <div className="space-y-2">
                                {existingMatches(item.id).map((album) => (
                                  <button
                                    key={album.id}
                                    type="button"
                                    onClick={() => {
                                      setExistingSearchById((current) => ({
                                        ...current,
                                        [item.id]: `${album.artist} - ${album.name}`,
                                      }));
                                      setSelectedExistingAlbumById((current) => ({
                                        ...current,
                                        [item.id]: album.id,
                                      }));
                                    }}
                                    className={[
                                      "block w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-muted/40",
                                      String(selectedExistingAlbumById[item.id]) === String(album.id)
                                        ? "border-foreground bg-muted/40"
                                        : "border-border/70",
                                    ].join(" ")}
                                  >
                                    {album.artist} - {album.name}
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="grid gap-2 sm:grid-cols-2">
                            <input
                              value={createForm(item).artist}
                              onChange={(event) =>
                                updateCreateForm(item.id, "artist", event.target.value)
                              }
                              className="rounded-md border border-border bg-background px-3 py-2 text-sm"
                              placeholder="Artist"
                            />
                            <input
                              value={createForm(item).name}
                              onChange={(event) =>
                                updateCreateForm(item.id, "name", event.target.value)
                              }
                              className="rounded-md border border-border bg-background px-3 py-2 text-sm"
                              placeholder="Album"
                            />
                            <input
                              value={createForm(item).listened_at}
                              onChange={(event) =>
                                updateCreateForm(item.id, "listened_at", event.target.value)
                              }
                              className="sm:col-span-2 rounded-md border border-border bg-background px-3 py-2 text-sm"
                              placeholder="Listened at"
                            />
                          </div>
                        )}

                        <Button
                          type="button"
                          size="sm"
                          onClick={() => handleResolve(item)}
                          disabled={pendingResolveId === item.id}
                        >
                          {pendingResolveId === item.id ? "Resolving..." : "Resolve row"}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-4 text-sm text-muted-foreground">No unresolved imports.</p>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default ImportHistoryDialog;
