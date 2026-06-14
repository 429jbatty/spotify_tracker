import {
  ChevronDown,
  ChevronUp,
  FileArchive,
  History,
  RefreshCcw,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  advancedImportStats,
  currentStepPercent,
  formatDuration,
  formatImportDate,
  importSummaryText,
  previewSummaryNote,
  sourceLabel,
  summaryCards,
  visibleImportStats,
} from "./importDialogConfig";
import { SourceGuide, SummaryStat } from "./ImportDialogFields";

function statusVariant(status) {
  if (status === "failed") return "destructive";
  if (status === "completed") return "secondary";
  return "outline";
}

function statusText(item) {
  if (item.status === "completed") return "Complete";
  if (item.status === "failed") return "Failed";
  return item.current_step_label || "Running";
}

function ProgressBar({ item, label = true }) {
  const percent = currentStepPercent(item);
  if (percent === null) return null;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-foreground transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
      {label ? (
        <p className="text-xs text-muted-foreground">
          {item.current_step_label || "Importing"} - {percent}%
        </p>
      ) : null}
    </div>
  );
}


export function ImportSourcePanel({
  activeSource,
  setActiveSource,
  lastfmUsername,
  setLastfmUsername,
  spotifyFile,
  setSpotifyFile,
  preview,
  summary,
  error,
  pendingPreview,
  pendingCommit,
  canCommit,
  onPreview,
  onCommit,
  onSpotifyUpload,
  onClearPreview,
  onClearError,
}) {
  const selectSource = (source) => {
    setActiveSource(source);
    onClearPreview();
    onClearError();
  };

  return (
    <section className="rounded-xl border border-border/70 bg-card p-5">
      <div className="grid grid-cols-2 gap-2 rounded-md border border-border/70 bg-background p-1">
        {[
          ["lastfm", "Last.fm"],
          ["spotify_import", "Spotify ZIP"],
        ].map(([source, label]) => (
          <button
            key={source}
            type="button"
            onClick={() => selectSource(source)}
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

      <div className="mt-5 flex flex-col gap-4">
        <SourceGuide source={activeSource} />

        {activeSource === "lastfm" ? (
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground">Last.fm username</span>
              <Input
                value={lastfmUsername}
                onChange={(event) => setLastfmUsername(event.target.value)}
                placeholder="your-lastfm-name"
              />
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" onClick={onPreview} disabled={pendingPreview}>
                {pendingPreview ? "Previewing..." : "Preview"}
              </Button>
              {preview ? (
                <Button type="button" variant="outline" onClick={onCommit} disabled={!canCommit || pendingCommit}>
                  {pendingCommit ? "Starting..." : "Start import"}
                </Button>
              ) : null}
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <label
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                const file = event.dataTransfer.files?.[0];
                if (file) setSpotifyFile(file);
              }}
              className="flex min-h-32 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-background p-5 text-center hover:bg-muted/30"
            >
              <FileArchive className="size-8 text-muted-foreground" />
              <span className="text-sm font-medium text-foreground">
                {spotifyFile ? spotifyFile.name : "Drop Spotify ZIP here"}
              </span>
              <span className="text-xs text-muted-foreground">
                Or choose the ZIP file from your computer.
              </span>
              <input
                type="file"
                accept=".zip,application/zip"
                className="sr-only"
                onChange={(event) => setSpotifyFile(event.target.files?.[0] || null)}
              />
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" onClick={onSpotifyUpload} disabled={!spotifyFile || pendingCommit}>
                {pendingCommit ? "Uploading..." : "Upload and start"}
              </Button>
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
            </div>
          </div>
        )}
      </div>

      {summary ? (
        <PreviewSummary activeSource={activeSource} summary={summary} />
      ) : null}
    </section>
  );
}

function PreviewSummary({ activeSource, summary }) {
  return (
    <section className="mt-5 rounded-lg border border-border/70 bg-background p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">Ready to import</p>
          <p className="mt-1 text-xs text-muted-foreground">{previewSummaryNote(summary)}</p>
        </div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {summaryCards(activeSource, summary).map((card) => (
          <SummaryStat key={card.label} label={card.label} value={card.value} />
        ))}
      </div>
    </section>
  );
}

export function ActiveImportStatus({ activeImport, pendingCommit }) {
  if (!pendingCommit && !activeImport) return null;

  const stats = visibleImportStats(activeImport?.summary);

  return (
    <section className="rounded-xl border border-border/70 bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">
            {activeImport ? activeImport.current_step_label || statusText(activeImport) : "Starting import..."}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {activeImport?.current_step_detail || "Preparing the import."}
          </p>
        </div>
        {activeImport?.estimated_seconds_remaining ? (
          <Badge variant="outline">ETA {formatDuration(activeImport.estimated_seconds_remaining)}</Badge>
        ) : null}
      </div>
      {activeImport ? (
        <div className="mt-4 flex flex-col gap-4">
          <ProgressBar item={activeImport} />
          {stats.length ? (
            <div className="grid gap-3 sm:grid-cols-3">
              {stats.map((stat) => (
                <SummaryStat key={stat.label} label={stat.label} value={stat.value} />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function ImportHistoryList({
  history,
  loadingHistory,
  pendingDeleteImportId,
  expandedLogIds,
  onRefresh,
  onDelete,
  onToggleAdvanced,
}) {
  return (
    <section className="rounded-xl border border-border/70 bg-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">Recent imports</p>
          <p className="text-xs text-muted-foreground">Completed runs and current status.</p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onRefresh}>
          <RefreshCcw className="size-4" />
        </Button>
      </div>

      {loadingHistory ? (
        <p className="mt-4 text-sm text-muted-foreground">Loading imports...</p>
      ) : history.length ? (
        <div className="mt-4 flex flex-col gap-3">
          {history.map((item) => (
            <ImportHistoryRow
              key={item.id}
              item={item}
              pendingDeleteImportId={pendingDeleteImportId}
              expanded={Boolean(expandedLogIds[item.id])}
              onDelete={onDelete}
              onToggleAdvanced={onToggleAdvanced}
            />
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">No imports yet.</p>
      )}
    </section>
  );
}

function ImportHistoryRow({
  item,
  pendingDeleteImportId,
  expanded,
  onDelete,
  onToggleAdvanced,
}) {
  const isActive = !["completed", "failed"].includes(item.status);
  const advancedStats = advancedImportStats(item);
  const stats = visibleImportStats(item.summary);

  return (
    <article className="rounded-lg border border-border/70 bg-background p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-foreground">
              {item.session_name || sourceLabel(item.source)}
            </p>
            <Badge variant={statusVariant(item.status)}>{statusText(item)}</Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {sourceLabel(item.source)}
            {item.source_user_id ? ` - ${item.source_user_id}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <History className="size-3.5" />
          <span>{formatImportDate(item.completed_at || item.started_at)}</span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8 text-muted-foreground hover:text-destructive"
            disabled={isActive || pendingDeleteImportId === item.id}
            onClick={() => onDelete(item)}
            aria-label={
              isActive
                ? `Import ${item.session_name || item.source} is still running`
                : `Delete import ${item.session_name || item.source}`
            }
            title={isActive ? "Wait for this import to finish before deleting it." : "Delete import"}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          {item.current_step_detail || importSummaryText(item.summary, item.status)}
        </p>
        {isActive ? <ProgressBar item={item} label={false} /> : null}
        {stats.length ? (
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {stats.map((stat) => (
              <span key={stat.label} className="rounded-md bg-muted px-2 py-1">
                {stat.label}: {Number(stat.value || 0).toLocaleString()}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {advancedStats.length ? (
        <div className="mt-3">
          <Button type="button" variant="outline" size="sm" onClick={() => onToggleAdvanced(item.id)}>
            {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
            {expanded ? "Hide advanced details" : "Advanced details"}
          </Button>
        </div>
      ) : null}

      {expanded && advancedStats.length ? (
        <div className="mt-3 grid gap-2 rounded-lg border border-border/70 bg-muted/20 p-3 sm:grid-cols-2">
          {advancedStats.map((stat) => (
            <div key={stat.label} className="rounded-md border border-border/60 bg-background px-2.5 py-2">
              <p className="text-xs text-muted-foreground">{stat.label}</p>
              <p className="mt-0.5 text-sm font-medium text-foreground">{stat.value}</p>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function ReviewQueue({
  reviewItems,
  resolveMode,
  setResolveModeById,
  existingSearchById,
  setExistingSearchById,
  selectedExistingAlbumById,
  setSelectedExistingAlbumById,
  existingMatches,
  createForm,
  updateCreateForm,
  pendingResolveId,
  onResolve,
}) {
  return (
    <section className="rounded-xl border border-border/70 bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">Unresolved sessions</p>
          <p className="text-xs text-muted-foreground">
            {reviewItems.length
              ? `${reviewItems.length.toLocaleString()} need a match before they can be added.`
              : "No sessions need review."}
          </p>
        </div>
        {reviewItems.length ? <Badge variant="outline">{reviewItems.length}</Badge> : null}
      </div>

      {reviewItems.length ? (
        <div className="mt-4 flex flex-col gap-3">
          {reviewItems.map((item) => (
            <ReviewQueueItem
              key={item.id}
              item={item}
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
              onResolve={onResolve}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function ReviewQueueItem({
  item,
  resolveMode,
  setResolveModeById,
  existingSearchById,
  setExistingSearchById,
  selectedExistingAlbumById,
  setSelectedExistingAlbumById,
  existingMatches,
  createForm,
  updateCreateForm,
  pendingResolveId,
  onResolve,
}) {
  return (
    <article className="rounded-lg border border-border/70 bg-background p-4">
      <p className="text-sm font-medium text-foreground">
        {item.artist}
        {item.album ? ` - ${item.album}` : item.track ? ` - ${item.track}` : ""}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {item.listened_at} - {sourceLabel(item.source)}
        {item.source_user_id ? ` - ${item.source_user_id}` : ""}
      </p>
      {item.status_detail ? <p className="mt-2 text-xs text-destructive">{item.status_detail}</p> : null}

      <div className="mt-3 flex flex-col gap-3 border-t border-border/70 pt-3">
        <div className="flex gap-2">
          {[
            ["existing", "Match existing"],
            ["create", "Create album"],
          ].map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              onClick={() =>
                setResolveModeById((current) => ({
                  ...current,
                  [item.id]: mode,
                }))
              }
              className={[
                "rounded-md px-2 py-1 text-xs",
                resolveMode(item.id) === mode
                  ? "bg-foreground text-background"
                  : "border border-border text-muted-foreground",
              ].join(" ")}
            >
              {label}
            </button>
          ))}
        </div>

        {resolveMode(item.id) === "existing" ? (
          <div className="flex flex-col gap-2">
            <Input
              value={existingSearchById[item.id] || ""}
              onChange={(event) =>
                setExistingSearchById((current) => ({
                  ...current,
                  [item.id]: event.target.value,
                }))
              }
              placeholder="Search existing albums"
            />
            {existingSearchById[item.id]?.trim() ? (
              <div className="flex flex-col gap-2">
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
            ) : null}
          </div>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            <Input
              value={createForm(item).artist}
              onChange={(event) => updateCreateForm(item.id, "artist", event.target.value)}
              placeholder="Artist"
            />
            <Input
              value={createForm(item).name}
              onChange={(event) => updateCreateForm(item.id, "name", event.target.value)}
              placeholder="Album"
            />
            <Input
              value={createForm(item).listened_at}
              onChange={(event) => updateCreateForm(item.id, "listened_at", event.target.value)}
              className="sm:col-span-2"
              placeholder="Listened at"
            />
          </div>
        )}

        <Button type="button" size="sm" onClick={() => onResolve(item)} disabled={pendingResolveId === item.id}>
          {pendingResolveId === item.id ? "Resolving..." : "Resolve"}
        </Button>
      </div>
    </article>
  );
}
