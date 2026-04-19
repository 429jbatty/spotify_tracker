import { useEffect, useMemo, useState } from "react";
import AlbumArtwork from "./AlbumArtwork";
import AlbumSidePanel from "./AlbumSidePanel";
import {
  getQualityIssueIds,
  QUALITY_ISSUES,
} from "./utils/albumFilters";
import { Sheet, SheetContent } from "@/components/ui/sheet";

function albumKey(album) {
  return album.id || album.release_group_mbid || `${album.artist}-${album.name}`;
}

function IssueCard({ issue, albums, active, onClick, pendingCount }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg border p-4 text-left transition-colors ${
        active
          ? "border-primary bg-primary/10"
          : "border-border bg-card hover:bg-muted"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground">{issue.label}</h2>
          <p className="mt-2 text-3xl font-semibold text-foreground">
            {albums.length}
          </p>
          {pendingCount > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              Checking {pendingCount}
            </p>
          )}
        </div>
        <span className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground">
          View
        </span>
      </div>
    </button>
  );
}

function AlbumIssueRow({ album, issues, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="grid w-full grid-cols-[3rem_1fr] gap-3 rounded-lg border border-border p-2 text-left hover:bg-muted"
    >
      <div className="h-12 w-12 overflow-hidden rounded-md">
        <AlbumArtwork album={album} />
      </div>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-foreground">{album.name}</p>
        <p className="truncate text-xs text-muted-foreground">{album.artist}</p>
        <div className="mt-2 flex flex-wrap gap-1">
          {issues.map((issue) => (
            <span
              key={issue}
              className="rounded-md bg-muted px-2 py-1 text-[11px] text-muted-foreground"
            >
              {QUALITY_ISSUES.find((item) => item.id === issue)?.label || issue}
            </span>
          ))}
        </div>
      </div>
    </button>
  );
}

function PageDataQuality({ albums, onDataChanged, onFilterSelect }) {
  const [selectedAlbum, setSelectedAlbum] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [artworkStatus, setArtworkStatus] = useState(() => new Map());
  const albumArray = useMemo(() => Object.values(albums || {}), [albums]);

  useEffect(() => {
    let cancelled = false;

    queueMicrotask(() => {
      if (cancelled) return;
      setArtworkStatus(
        new Map(albumArray.map((album) => [albumKey(album), "pending"]))
      );
    });

    albumArray.forEach((album) => {
      const imageUrl = String(album.image_url || "").trim();
      const key = albumKey(album);

      const setStatus = (status) => {
        if (cancelled) return;
        setArtworkStatus((current) => {
          const next = new Map(current);
          next.set(key, status);
          return next;
        });
      };

      if (!imageUrl || imageUrl.toLowerCase().includes("placeholder")) {
        queueMicrotask(() => setStatus("failed"));
        return;
      }

      const image = new Image();
      image.onload = () => setStatus("loaded");
      image.onerror = () => setStatus("failed");
      image.src = imageUrl;
    });

    return () => {
      cancelled = true;
    };
  }, [albumArray]);

  const artworkPendingCount = useMemo(() => {
    return albumArray.filter(
      (album) => artworkStatus.get(albumKey(album)) === "pending"
    ).length;
  }, [albumArray, artworkStatus]);

  const artworkFailedKeys = useMemo(() => {
    return new Set(
      albumArray
        .filter((album) => artworkStatus.get(albumKey(album)) === "failed")
        .map(albumKey)
      );
  }, [albumArray, artworkStatus]);

  const issueMap = useMemo(() => {
    const grouped = Object.fromEntries(QUALITY_ISSUES.map((issue) => [issue.id, []]));

    albumArray.forEach((album) => {
      const issues = getQualityIssueIds(album).filter(
        (issueId) => issueId !== "missing-artwork"
      );

      if (artworkFailedKeys.has(albumKey(album))) {
        issues.unshift("missing-artwork");
      }

      issues.forEach((issueId) => {
        grouped[issueId].push(album);
      });
    });

    return grouped;
  }, [albumArray, artworkFailedKeys]);

  const albumsWithIssues = useMemo(() => {
    const rows = albumArray
      .map((album) => ({
        album,
        issues: [
          ...(artworkFailedKeys.has(albumKey(album)) ? ["missing-artwork"] : []),
          ...getQualityIssueIds(album).filter(
            (issueId) => issueId !== "missing-artwork"
          ),
        ],
      }))
      .filter((item) => item.issues.length > 0);

    const filteredRows = selectedIssue
      ? rows.filter((item) => item.issues.includes(selectedIssue))
      : rows;

    return filteredRows.sort((a, b) => b.issues.length - a.issues.length);
  }, [albumArray, artworkFailedKeys, selectedIssue]);

  const openAlbum = (album) => {
    setSelectedAlbum(album);
    setPanelOpen(true);
  };

  const updateSelectedAlbum = (album) => {
    setSelectedAlbum((current) => (current ? { ...current, ...album } : album));
  };

  const handleAlbumDeleted = () => {
    setSelectedAlbum(null);
    setPanelOpen(false);
  };

  return (
    <>
      <div className="space-y-6 px-6">
        <section>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            Data Quality
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Albums that need metadata cleanup.
          </p>
          {artworkPendingCount > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              Checking artwork URLs in the browser. Pending albums are not counted as unresolved.
            </p>
          )}
        </section>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-5">
          {QUALITY_ISSUES.map((issue) => (
            <IssueCard
              key={issue.id}
              issue={issue}
              albums={issueMap[issue.id]}
              active={selectedIssue === issue.id}
              onClick={() =>
                setSelectedIssue((current) =>
                  current === issue.id ? null : issue.id
                )
              }
              pendingCount={issue.id === "missing-artwork" ? artworkPendingCount : 0}
            />
          ))}
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-sm font-semibold text-foreground">
              {selectedIssue
                ? QUALITY_ISSUES.find((issue) => issue.id === selectedIssue)?.label
                : "Albums with open issues"}
            </h2>
            {selectedIssue && (
              <button
                type="button"
                onClick={() => setSelectedIssue(null)}
                className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                Show all
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {albumsWithIssues.map(({ album, issues }) => (
              <AlbumIssueRow
                key={album.id || album.release_group_mbid || `${album.artist}-${album.name}`}
                album={album}
                issues={issues}
                onClick={() => openAlbum(album)}
              />
            ))}
          </div>
        </section>
      </div>

      <Sheet open={panelOpen} onOpenChange={setPanelOpen}>
        <SheetContent
          side="right"
          className="w-[650px] sm:w-[750px] overflow-y-auto p-6"
        >
          {selectedAlbum && (
            <AlbumSidePanel
              album={selectedAlbum}
              onFilterSelect={onFilterSelect}
              onAlbumUpdated={updateSelectedAlbum}
              onAlbumDeleted={handleAlbumDeleted}
              onDataChanged={onDataChanged}
            />
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}

export default PageDataQuality;
