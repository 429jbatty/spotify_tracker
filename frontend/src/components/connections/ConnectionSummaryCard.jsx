import { ArrowRight, Disc3, Network, UsersRound } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatRoleLabel,
  formatRoleSummary,
  getPrimaryRole,
} from "./connectionFormatters";

function AlbumPreviewList({ albums }) {
  if (!albums?.length) return null;

  return (
    <div className="space-y-2">
      {albums.slice(0, 3).map((album) => (
        <div
          key={album.album_id}
          className="rounded-md border border-border/70 bg-background/60 px-3 py-2"
        >
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-foreground">{album.name}</p>
            <p className="truncate text-xs text-muted-foreground">{album.artist}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function ConnectionSummaryCard({ compact = false, contributor, onFocus, onInspect }) {
  const primaryRole = getPrimaryRole(contributor.role_buckets);

  if (compact) {
    return (
      <button
        aria-label={`Explore from ${contributor.person_name}`}
        className="flex min-w-0 items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3 text-left transition hover:border-primary/40 hover:bg-muted/40"
        onClick={() => onFocus?.(contributor)}
        type="button"
      >
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold text-foreground">
            {contributor.person_name}
          </span>
          <span className="mt-1 block truncate text-xs text-muted-foreground">
            {formatRoleLabel(primaryRole)} · {contributor.connected_album_count} albums
          </span>
        </span>
        <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
      </button>
    );
  }

  return (
    <Card className="rounded-lg">
      <CardHeader className="gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Badge variant="outline">{formatRoleLabel(primaryRole)}</Badge>
            <CardTitle className="mt-3 truncate text-lg">
              {contributor.person_name}
            </CardTitle>
          </div>
          <Button
            aria-label={`Explore from ${contributor.person_name}`}
            onClick={() => onFocus?.(contributor)}
            size="icon-sm"
            variant="ghost"
          >
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-md bg-muted/70 p-2">
            <Disc3 className="mb-2 size-4 text-primary" />
            <p className="text-sm font-semibold text-foreground">
              {contributor.connected_album_count}
            </p>
            <p className="text-[11px] text-muted-foreground">albums</p>
          </div>
          <div className="rounded-md bg-muted/70 p-2">
            <UsersRound className="mb-2 size-4 text-chart-2" />
            <p className="text-sm font-semibold text-foreground">
              {contributor.distinct_primary_artist_count}
            </p>
            <p className="text-[11px] text-muted-foreground">artists</p>
          </div>
          <div className="rounded-md bg-muted/70 p-2">
            <Network className="mb-2 size-4 text-chart-3" />
            <p className="text-sm font-semibold text-foreground">
              {Object.keys(contributor.role_buckets || {}).length}
            </p>
            <p className="text-[11px] text-muted-foreground">roles</p>
          </div>
        </div>

        <p className="text-sm leading-6 text-muted-foreground">
          {formatRoleSummary(contributor.role_buckets)}
        </p>

        <AlbumPreviewList albums={contributor.representative_albums} />

        <div className="flex gap-2">
          <Button
            className="flex-1"
            onClick={() => onFocus?.(contributor)}
            size="sm"
            variant="outline"
          >
            Explore from here
          </Button>
          <Button
            onClick={() => onInspect(contributor)}
            size="sm"
            variant="ghost"
          >
            Details
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
