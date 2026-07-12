import { useMemo, useState } from "react";
import {
  ArrowRight,
  Disc3,
  LoaderCircle,
  LocateFixed,
  Network,
  Sparkles,
  UsersRound,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatCount,
  formatRoleLabel,
} from "./connectionFormatters";
import {
  buildConnectionGraphModel,
  previewGraphState,
  relatedIds,
  selectedLinks,
} from "./connectionGraphModel";
import { connectionRoleLabels } from "./connectionRoles";
import { connectionSearchResult } from "./connectionSearchStatus";
import { resolveEffectiveSelectedId } from "./connectionSelection";

const GRAPH_WIDTH = 980;
const GRAPH_HEIGHT = 520;

const ROLE_COLORS = {
  producer: "#2563eb",
  writer_composer: "#16a34a",
  mixing_mastering: "#c2410c",
  engineering: "#7c3aed",
  performer: "#db2777",
  other: "#64748b",
};

const NODE_COLORS = {
  contributor: "#111827",
  album: "#f8fafc",
};

function nodeLabel(node) {
  if (!node) return "";
  if (node.type === "album") return `${node.name} by ${node.artist}`;
  return node.name;
}

function strongestRoleNames(roleBuckets = {}, limit = 2) {
  return Object.entries(roleBuckets)
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit)
    .map(([role]) => formatRoleLabel(role));
}

function albumTitle(album) {
  if (!album) return "Album";
  return `${album.name} by ${album.artist}`;
}

function albumNodeId(album) {
  return album?.album_id ? `album:${album.album_id}` : null;
}

function contributorNodeId(contributor) {
  return contributor?.person_key ? `contributor:${contributor.person_key}` : null;
}

function pathNodeRoles(albumConnection) {
  const roles = new Map();
  const bestPath = albumConnection?.best_path;
  if (!bestPath) {
    if (albumConnection?.album_a?.album_id) {
      roles.set(`album:${albumConnection.album_a.album_id}`, "endpoint");
    }
    if (albumConnection?.album_b?.album_id) {
      roles.set(`album:${albumConnection.album_b.album_id}`, "endpoint");
    }
    return roles;
  }

  const albumIds = bestPath.album_ids || [];
  albumIds.forEach((albumId, index) => {
    const isEndpoint = index === 0 || index === albumIds.length - 1;
    roles.set(`album:${albumId}`, isEndpoint ? "endpoint" : "intermediate-album");
  });
  (bestPath.contributor_keys || []).forEach((personKey) => {
    roles.set(`contributor:${personKey}`, "intermediate-contributor");
  });
  return roles;
}

function orderedPathNodeIds(albumConnection) {
  const steps = albumConnection?.best_path?.steps || [];
  if (steps.length === 0) return [];

  const ids = [albumNodeId(steps[0].from_album)];
  steps.forEach((step) => {
    ids.push(contributorNodeId(step.contributor));
    ids.push(albumNodeId(step.to_album));
  });
  return ids.filter(Boolean);
}

function endpointNodeIds(albumConnection) {
  return [
    albumNodeId(albumConnection?.album_a),
    albumNodeId(albumConnection?.album_b),
  ].filter(Boolean);
}

function graphTitle({ albumConnection, selectedNode }) {
  if (selectedNode?.type === "contributor") return `${selectedNode.name}'s credit network`;
  if (selectedNode?.type === "album") return `Albums connected to ${selectedNode.name}`;
  if (albumConnection) {
    return `Credit path between ${albumConnection.album_a?.name || "Album"} and ${albumConnection.album_b?.name || "Album"}`;
  }
  return "Explore your credit network";
}

function rankStartingNodes(model) {
  const contributors = model.contributors
    .slice()
    .sort((left, right) => (
      (right.connected_album_count || 0) - (left.connected_album_count || 0)
      || (right.distinct_primary_artist_count || 0) - (left.distinct_primary_artist_count || 0)
      || left.name.localeCompare(right.name)
    ))
    .slice(0, 3);
  const albums = model.albums
    .slice()
    .sort((left, right) => (
      (right.connected_contributor_count || 0) - (left.connected_contributor_count || 0)
      || left.artist.localeCompare(right.artist)
      || left.name.localeCompare(right.name)
    ))
    .slice(0, Math.max(0, 5 - contributors.length));
  return [...contributors, ...albums].slice(0, 5);
}

function recommendationReason(node) {
  if (node.type === "album") {
    const contributorCount = node.connected_contributor_count || 0;
    if (contributorCount > 0) {
      return `Connected through ${formatCount(contributorCount, "recurring contributor")}`;
    }
    return node.artist;
  }
  const albumText = formatCount(node.connected_album_count || 0, "album");
  const artistText = formatCount(node.distinct_primary_artist_count || 0, "artist");
  return `${albumText} across ${artistText}`;
}

function clipId(nodeId) {
  return `clip-${nodeId.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

function dynamicLayoutRadius(count, compact, medium, full) {
  if (count <= 3) return compact;
  if (count <= 8) return medium;
  return full;
}

function withSequentialConnectionPositions(model, albumConnection) {
  if (!albumConnection) return null;

  const pathIds = orderedPathNodeIds(albumConnection);
  const orderedIds = pathIds.length > 0 ? pathIds : endpointNodeIds(albumConnection);
  if (orderedIds.length === 0) return null;

  const orderedSet = new Set(orderedIds);
  const positioned = new Map();
  const pathStartX = 86;
  const pathEndX = GRAPH_WIDTH - 86;
  const pathWidth = pathEndX - pathStartX;
  const albumY = 216;
  const contributorY = 306;

  orderedIds.forEach((nodeId, index) => {
    const node = model.nodes.find((item) => item.id === nodeId);
    if (!node) return;
    const x = orderedIds.length === 1
      ? GRAPH_WIDTH / 2
      : pathStartX + (pathWidth * index) / (orderedIds.length - 1);
    positioned.set(node.id, {
      ...node,
      x,
      y: node.type === "contributor" ? contributorY : albumY,
    });
  });

  const sideNodes = model.nodes.filter((node) => !orderedSet.has(node.id));
  const columns = Math.max(Math.ceil(sideNodes.length / 2), 1);
  sideNodes.forEach((node, index) => {
    const row = index % 2;
    const column = Math.floor(index / 2);
    positioned.set(node.id, {
      ...node,
      x: pathStartX + (pathWidth * (column + 0.5)) / columns,
      y: row === 0 ? 92 : 438,
    });
  });

  const nodes = model.nodes.map((node) => positioned.get(node.id)).filter(Boolean);
  return {
    nodes,
    links: model.links,
    contributors: nodes.filter((node) => node.type === "contributor"),
    albums: nodes.filter((node) => node.type === "album"),
  };
}

function withRadialPositions(model) {
  const centerX = GRAPH_WIDTH / 2;
  const centerY = GRAPH_HEIGHT / 2;
  const contributorRadius = dynamicLayoutRadius(model.contributors.length, 66, 94, 116);
  const albumRadiusX = dynamicLayoutRadius(model.albums.length, 210, 315, 400);
  const albumRadiusY = dynamicLayoutRadius(model.albums.length, 130, 170, 205);
  const positioned = new Map();

  model.contributors.forEach((node, index) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * index) / Math.max(model.contributors.length, 1);
    positioned.set(node.id, {
      ...node,
      x: centerX + Math.cos(angle) * contributorRadius,
      y: centerY + Math.sin(angle) * contributorRadius,
    });
  });

  model.albums.forEach((node, index) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * index) / Math.max(model.albums.length, 1);
    positioned.set(node.id, {
      ...node,
      x: centerX + Math.cos(angle) * albumRadiusX,
      y: centerY + Math.sin(angle) * albumRadiusY,
    });
  });

  const nodes = model.nodes.map((node) => positioned.get(node.id));
  return {
    nodes,
    links: model.links,
    contributors: nodes.filter((node) => node.type === "contributor"),
    albums: nodes.filter((node) => node.type === "album"),
  };
}

function withPositions(model, albumConnection) {
  return withSequentialConnectionPositions(model, albumConnection) || withRadialPositions(model);
}

function truncateGraphLabel(label, limit = 20) {
  if (!label || label.length <= limit) return label;
  return `${label.slice(0, limit - 1)}…`;
}

function compactPathItems(albumConnection) {
  const bestPath = albumConnection?.best_path;
  if (!bestPath?.steps?.length) return [];

  const items = [
    {
      id: albumNodeId(bestPath.steps[0].from_album),
      label: bestPath.steps[0].from_album.name,
      meta: bestPath.steps[0].from_album.artist,
      type: "album",
    },
  ];

  bestPath.steps.forEach((step) => {
    const roles = strongestRoleNames(step.contributor.role_buckets, 3);
    items.push({
      id: contributorNodeId(step.contributor),
      label: step.contributor.person_name,
      meta: roles.length > 0 ? roles.join(", ") : "Shared credit",
      type: "contributor",
    });
    items.push({
      id: albumNodeId(step.to_album),
      label: step.to_album.name,
      meta: step.to_album.artist,
      type: "album",
    });
  });

  return items;
}

function PathItemButton({ item, onSelectNode }) {
  const isAlbum = item.type === "album";
  const IconComponent = isAlbum ? Disc3 : UsersRound;
  const wrapperClass = isAlbum ? "" : "ml-7";
  const buttonClass = isAlbum
    ? "border-border bg-background hover:bg-muted"
    : "border-sky-200 bg-sky-50/80 hover:bg-sky-100 dark:border-sky-900/70 dark:bg-sky-950/30 dark:hover:bg-sky-950/50";
  const iconClass = isAlbum
    ? "border-border bg-muted text-muted-foreground"
    : "border-sky-200 bg-background text-sky-700 dark:border-sky-900 dark:text-sky-300";

  return (
    <div className={`min-w-0 flex-1 ${wrapperClass}`}>
      <button
        className={`flex w-full min-w-0 items-start gap-2 rounded-md border px-2.5 py-2 text-left transition ${buttonClass}`}
        onClick={() => item.id && onSelectNode?.(item.id)}
        type="button"
      >
        <span className={`mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full border ${iconClass}`}>
          <IconComponent className="size-3.5" />
        </span>
        <span className="min-w-0">
          <span className="block break-words text-xs font-semibold leading-snug text-foreground">
            {item.label}
          </span>
          <span className="mt-0.5 block break-words text-[11px] leading-snug text-muted-foreground">
            {isAlbum ? "Album" : "Person"} · {item.meta}
          </span>
        </span>
      </button>
    </div>
  );
}

function GraphNode({
  active,
  dimmed,
  labeled,
  node,
  onPreviewNode,
  onSelect,
  pathRole,
  previewed,
  previewRelated,
  selected,
  suggested,
}) {
  const isContributor = node.type === "contributor";
  const isEndpoint = pathRole === "endpoint";
  const isPathNode = Boolean(pathRole);
  const radius = isContributor
    ? isEndpoint ? 16 : isPathNode ? 14 : 11
    : isEndpoint ? 12 : isPathNode ? 10 : 8;
  const fill = isContributor ? NODE_COLORS.contributor : NODE_COLORS.album;
  const roleStroke = isContributor ? ROLE_COLORS[node.primaryRole] || ROLE_COLORS.other : "#334155";
  const stroke = selected
    ? "#0f172a"
    : isEndpoint
      ? "#f59e0b"
      : pathRole === "intermediate-album"
        ? "#0f766e"
        : pathRole === "intermediate-contributor"
          ? "#0369a1"
          : roleStroke;
  const baseAlbumSize = selected ? 66 : isEndpoint ? 64 : isPathNode ? 58 : active ? 54 : 48;
  const albumSize = previewed && !selected
    ? baseAlbumSize + 8
    : previewRelated && !selected
      ? baseAlbumSize + 3
      : baseAlbumSize;
  const albumX = node.x - albumSize / 2;
  const albumY = node.y - albumSize / 2;
  const albumCornerRadius = 5;
  const strokeWidth = selected ? 4.5 : isEndpoint ? 4 : isPathNode ? 3.4 : suggested ? 3 : 2;
  const opacity = dimmed ? 0.16 : 1;
  const labelYOffset = node.y < GRAPH_HEIGHT / 2 ? -18 : 26;
  const contributorRadius = selected
    ? radius + 5
    : previewed
      ? radius + 5
      : active
        ? radius + 3
        : suggested
          ? radius + 2
          : radius;
  const displayContributorRadius = previewRelated && !previewed && !selected
    ? contributorRadius + 1.5
    : contributorRadius;
  const displayStrokeWidth = previewed && !selected ? strokeWidth + 1 : strokeWidth;

  return (
    <g
      aria-label={nodeLabel(node)}
      className="cursor-pointer outline-none"
      onClick={() => onSelect(node.id)}
      onFocus={() => onPreviewNode(node.id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(node.id);
        }
      }}
      onPointerEnter={(event) => {
        if (event.pointerType !== "touch") onPreviewNode(node.id);
      }}
      onPointerLeave={() => onPreviewNode(null)}
      onBlur={() => onPreviewNode(null)}
      role="button"
      tabIndex={0}
    >
      {node.type === "album" && node.image_url ? (
        <>
          <defs>
            <clipPath id={clipId(node.id)}>
              <rect
                height={albumSize}
                rx={albumCornerRadius}
                width={albumSize}
                x={albumX}
                y={albumY}
              />
            </clipPath>
          </defs>
          <image
            clipPath={`url(#${clipId(node.id)})`}
            className="transition-all duration-200 ease-out motion-reduce:transition-none"
            height={albumSize}
            href={node.image_url}
            opacity={dimmed ? 0.18 : 1}
            preserveAspectRatio="xMidYMid slice"
            width={albumSize}
            x={albumX}
            y={albumY}
          />
          <rect
            fill="transparent"
            height={albumSize}
            opacity={dimmed ? 0.22 : 1}
            rx={albumCornerRadius}
            stroke={stroke}
                className="transition-all duration-200 ease-out motion-reduce:transition-none"
                strokeWidth={displayStrokeWidth}
            width={albumSize}
            x={albumX}
            y={albumY}
          />
        </>
      ) : node.type === "album" ? (
        <rect
          fill={fill}
          height={albumSize}
          opacity={opacity}
          rx={albumCornerRadius}
          stroke={stroke}
            className="transition-all duration-200 ease-out motion-reduce:transition-none"
            strokeWidth={displayStrokeWidth}
          width={albumSize}
          x={albumX}
          y={albumY}
        />
      ) : (
        <circle
          cx={node.x}
          cy={node.y}
          fill={fill}
          opacity={opacity}
          className="transition-all duration-200 ease-out motion-reduce:transition-none"
          r={displayContributorRadius}
          stroke={stroke}
          strokeWidth={displayStrokeWidth}
        />
      )}
      {labeled && isContributor && !dimmed && (
        <text
          aria-hidden="true"
          fill="#0f172a"
          fontSize="18"
          fontWeight="600"
          paintOrder="stroke"
          pointerEvents="none"
          stroke="#f8fafc"
          strokeLinejoin="round"
          strokeWidth="6"
          textAnchor="middle"
          x={node.x}
          y={node.y + labelYOffset}
        >
          {truncateGraphLabel(node.name)}
        </text>
      )}
      <title>{nodeLabel(node)}</title>
    </g>
  );
}

function GraphPreview({ node }) {
  if (!node) return null;

  const width = 208;
  const height = 58;
  const x = node.x > GRAPH_WIDTH - width - 28 ? node.x - width - 24 : node.x + 24;
  const y = Math.max(12, Math.min(GRAPH_HEIGHT - height - 12, node.y - height / 2));
  const subtitle = node.type === "album"
    ? node.artist
    : formatRoleLabel(node.primaryRole);

  return (
    <g
      aria-hidden="true"
      className="pointer-events-none motion-reduce:transition-none"
      data-testid="graph-node-preview"
    >
      <rect
        className="transition-opacity duration-150 ease-out motion-reduce:transition-none"
        fill="#0f172a"
        height={height}
        opacity="0.94"
        rx="8"
        width={width}
        x={x}
        y={y}
      />
      <text fill="#f8fafc" fontSize="14" fontWeight="600" x={x + 12} y={y + 24}>
        {truncateGraphLabel(node.name, 27)}
      </text>
      <text fill="#cbd5e1" fontSize="12" x={x + 12} y={y + 43}>
        {truncateGraphLabel(subtitle, 31)}
      </text>
    </g>
  );
}

function SuggestedNodeButton({ node, onSelectNode }) {
  const roles = strongestRoleNames(node.role_buckets);
  const description = recommendationReason(node);
  const meta = node.type === "album"
    ? "Album"
    : roles.length > 0
      ? roles.join(", ")
      : "Contributor";

  return (
    <button
      className="w-full min-w-0 max-w-full overflow-hidden rounded-md border border-transparent bg-transparent px-3 py-2 text-left transition hover:bg-background hover:shadow-xs"
      onClick={() => onSelectNode?.(node.id)}
      type="button"
    >
      <span className="flex min-w-0 items-center justify-between gap-3">
        <span className="min-w-0 max-w-full flex-1">
          <span className="block break-words text-sm font-medium leading-snug text-foreground">
            {node.name}
          </span>
          <span className="mt-0.5 block break-words text-xs leading-snug text-muted-foreground">
            {meta} · {description}
          </span>
        </span>
        <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
      </span>
    </button>
  );
}

function DetailShell({ children }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-lg border border-border/80 bg-card/80 p-4 shadow-xs">
      <div className="grid w-full min-w-0 max-w-full gap-4 overflow-hidden">{children}</div>
    </div>
  );
}

function DetailList({ children, emphasis = false }) {
  return (
    <div
      className={`grid gap-1 rounded-lg border p-1 ${
        emphasis
          ? "border-primary/20 bg-primary/5"
          : "border-border/70 bg-muted/35"
      }`}
    >
      {children}
    </div>
  );
}

function DetailActions({ children }) {
  return (
    <div className="grid w-full min-w-0 max-w-full grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1">
      {children}
    </div>
  );
}

function DetailActionButton({ children, icon, onClick, variant = "outline" }) {
  const IconComponent = icon;

  return (
    <Button
      className="h-auto min-h-8 !w-full !min-w-0 max-w-full shrink justify-start whitespace-normal px-2.5 py-1.5 text-left leading-snug"
      onClick={onClick}
      size="sm"
      type="button"
      variant={variant}
    >
      {IconComponent && <IconComponent className="mr-1.5 size-3.5" />}
      <span className="min-w-0 break-words">{children}</span>
    </Button>
  );
}

function DetailStat({ icon, label, value, tone = "text-primary" }) {
  const IconComponent = icon;

  return (
    <div className="min-w-0 p-2.5">
      <IconComponent className={`mb-2 size-4 ${tone}`} />
      <p className="text-sm font-semibold text-foreground">{value}</p>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  );
}

function RelatedNodeButton({ meta: metaOverride, node, onSelectNode, roles = [] }) {
  const meta = metaOverride || (node.type === "album"
    ? node.artist
    : strongestRoleNames(node.role_buckets, 2).join(", ") || "Contributor");

  return (
    <button
      className="w-full min-w-0 max-w-full rounded-md border border-transparent bg-transparent px-3 py-2 text-left transition hover:bg-background hover:shadow-xs"
      onClick={() => onSelectNode?.(node.id)}
      type="button"
    >
      <span className="block break-words text-sm font-medium leading-snug text-foreground">
        {node.name}
      </span>
      {meta && (
        <span className="mt-0.5 block break-words text-xs leading-snug text-muted-foreground">
          {meta}
        </span>
      )}
      {roles.length > 0 && (
        <span className="mt-2 flex flex-wrap gap-1">
          {roles.map((role) => (
            <span
              className="rounded-md border border-border bg-background px-1.5 py-0.5 text-[11px] font-medium leading-none text-muted-foreground"
              key={role}
            >
              {role}
            </span>
          ))}
        </span>
      )}
    </button>
  );
}

function RelatedNodeGroup({ children, count, initialCount = 4 }) {
  const [expanded, setExpanded] = useState(false);
  const items = Array.isArray(children) ? children : [children];
  const visibleItems = expanded ? items : items.slice(0, initialCount);

  return (
    <>
      <DetailList>{visibleItems}</DetailList>
      {count > initialCount && (
        <Button
          className="h-auto justify-start px-0 text-xs"
          onClick={() => setExpanded((current) => !current)}
          size="sm"
          type="button"
          variant="link"
        >
          {expanded ? "Show fewer" : `Show ${count - initialCount} more`}
        </Button>
      )}
    </>
  );
}

function GraphDetail({
  albumConnection,
  node,
  connectedNodes,
  links,
  onFocusNode,
  onInspectContributor,
  onOpenAlbum,
  onSelectNode,
  startingNodes,
}) {
  if (albumConnection && !node) {
    const shared = albumConnection.shared_contributors || [];
    const bestPath = albumConnection.best_path;
    const alternatePaths = albumConnection.alternate_paths || [];
    const hasPath = Boolean(bestPath);
    const searchResult = connectionSearchResult(albumConnection);
    const pathItems = compactPathItems(albumConnection);
    return (
      <DetailShell>
        <div className="w-full min-w-0 max-w-full">
          <Badge className="max-w-full whitespace-normal text-left leading-snug" variant="outline">
            Album path
          </Badge>
          <h3 className="mt-3 w-full min-w-0 max-w-full break-words text-base font-semibold leading-snug text-foreground">
            {searchResult.title}
          </h3>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {searchResult.detail || (hasPath
              ? `${formatCount(bestPath.hop_count, "credit step")} connects ${albumTitle(albumConnection.album_a)} to ${albumTitle(albumConnection.album_b)}.`
              : `${albumTitle(albumConnection.album_a)} and ${albumTitle(albumConnection.album_b)} do not currently connect within ${formatCount(albumConnection.max_contributor_hops || 2, "contributor hop")} after the normal identity and primary-artist filters.`)}
          </p>
        </div>

        {hasPath && (
          <>
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Path
              </h4>
              <div className="mt-2 grid gap-2">
                {pathItems.map((item, index) => (
                  <div
                    className="flex min-w-0 items-center gap-2"
                    key={`${item.id}-${index}`}
                  >
                    {index > 0 ? (
                      <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />
                    ) : (
                      <span className="size-3.5 shrink-0" />
                    )}
                    <PathItemButton item={item} onSelectNode={onSelectNode} />
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-2 text-sm leading-6 text-muted-foreground">
              <p>
                Connected through {formatCount(bestPath.hop_count, "shared-credit link")} across {formatCount((bestPath.album_ids || []).length, "album")}.
              </p>
              {bestPath.hop_count === 1 && shared.length > 1 && (
                <p>
                  Alternate direct paths are available through {shared.slice(1, 4).map((item) => item.person_name).join(", ")}.
                </p>
              )}
              {bestPath.hop_count > 1 && alternatePaths.length > 0 && (
                <p>
                  Alternate paths are available with {alternatePaths.slice(0, 3).map((path) => formatCount(path.hop_count, "step")).join(", ")}.
                </p>
              )}
            </div>

            <div className="grid gap-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Continue exploring
              </h4>
              <DetailActions>
                {bestPath.steps.slice(0, 3).map((step) => (
                  <DetailActionButton
                    key={step.contributor.person_key}
                    onClick={() => onSelectNode?.(contributorNodeId(step.contributor))}
                  >
                    Follow {step.contributor.person_name}
                  </DetailActionButton>
                ))}
              </DetailActions>
            </div>
          </>
        )}
      </DetailShell>
    );
  }

  if (!node) {
    return (
      <DetailShell>
        <div className="flex min-w-0 items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          <p className="text-sm font-medium text-foreground">Recommended starts</p>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">
          Strong entry points based on connected albums and artist breadth.
        </p>
        <DetailList>
          {startingNodes.map((item) => (
            <SuggestedNodeButton
              key={item.id}
              node={item}
              onSelectNode={onSelectNode}
            />
          ))}
        </DetailList>
        <div className="rounded-md bg-muted/60 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            How to explore
          </p>
          <ol className="mt-2 list-inside list-decimal space-y-1 text-sm text-muted-foreground">
            <li>Choose a recommended starting point.</li>
            <li>Select any album or contributor, then explore from there to rebuild the graph around it.</li>
            <li>Follow another connection outward.</li>
          </ol>
        </div>
      </DetailShell>
    );
  }

  if (node.type === "album") {
    const connectedContributors = connectedNodes.filter((item) => item.type === "contributor");
    return (
      <DetailShell>
        <div className="grid w-full min-w-0 max-w-full gap-3 overflow-hidden">
          <div className="w-full min-w-0 max-w-full space-y-2 overflow-hidden">
            <Badge className="max-w-full whitespace-normal text-left leading-snug" variant="outline">
              Album
            </Badge>
            <h3 className="w-full min-w-0 max-w-full break-words text-base font-semibold leading-snug text-foreground">
              {node.name}
            </h3>
            <p className="w-full min-w-0 max-w-full break-words text-sm leading-snug text-muted-foreground">{node.artist}</p>
          </div>
          <DetailActions>
            <DetailActionButton icon={LocateFixed} onClick={() => onFocusNode?.(node.id)} variant="default">
              Explore from here
            </DetailActionButton>
            <DetailActionButton onClick={() => onOpenAlbum?.(node.album_id)} variant="ghost">
              Open album
            </DetailActionButton>
          </DetailActions>
        </div>

        <div className="grid w-full min-w-0 max-w-full gap-2 overflow-hidden">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Explore through these contributors
          </h4>
          <RelatedNodeGroup count={connectedContributors.length}>
            {connectedContributors.map((contributor) => (
              <RelatedNodeButton
                key={contributor.id}
                node={contributor}
                onSelectNode={onSelectNode}
              />
            ))}
          </RelatedNodeGroup>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">
          Explore from here rebuilds the graph around this album and its credited contributors.
        </p>
      </DetailShell>
    );
  }

  const contributorPayload = {
    person_key: node.person_key,
    person_name: node.name,
    person_mbid: node.person_mbid,
    connected_album_count: node.connected_album_count,
    distinct_primary_artist_count: node.distinct_primary_artist_count,
    role_buckets: node.role_buckets,
    quality_flags: node.quality_flags,
    representative_albums: [],
  };
  const connectedAlbums = connectedNodes.filter((item) => item.type === "album");

  return (
    <DetailShell>
      <div className="grid w-full min-w-0 max-w-full gap-3 overflow-hidden">
        <div className="w-full min-w-0 max-w-full space-y-2 overflow-hidden">
          <Badge className="max-w-full whitespace-normal text-left leading-snug" variant="outline">
            {formatRoleLabel(node.primaryRole)}
          </Badge>
          <h3 className="w-full min-w-0 max-w-full break-words text-base font-semibold leading-snug text-foreground">
            {node.name}
          </h3>
        </div>
        <DetailActions>
          <DetailActionButton icon={LocateFixed} onClick={() => onFocusNode?.(node.id)} variant="default">
            Explore from here
          </DetailActionButton>
          <DetailActionButton onClick={() => onInspectContributor?.(contributorPayload)} variant="ghost">
            Details
          </DetailActionButton>
        </DetailActions>
      </div>

      <p className="text-sm leading-6 text-muted-foreground">
        Explore from here rebuilds the graph around this contributor and their connected albums.
      </p>

      <div className="grid w-full min-w-0 max-w-full gap-2 overflow-hidden">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Explore these albums
        </h4>
        <RelatedNodeGroup count={connectedAlbums.length}>
          {connectedAlbums.map((album) => (
            <RelatedNodeButton
              key={album.id}
              meta={album.artist}
              node={album}
              onSelectNode={onSelectNode}
              roles={connectionRoleLabels(node, album, links)}
            />
          ))}
        </RelatedNodeGroup>
      </div>

      <details className="group rounded-md border border-border/70 bg-muted/30 p-3">
        <summary className="cursor-pointer text-xs font-semibold text-muted-foreground">
          About this contributor
        </summary>
        <div className="mt-3 grid grid-cols-3 divide-x divide-border/70 overflow-hidden rounded-lg border border-border/70 bg-background/60">
          <DetailStat icon={Disc3} label="albums" value={node.connected_album_count} />
          <DetailStat icon={UsersRound} label="artists" tone="text-chart-2" value={node.distinct_primary_artist_count} />
          <DetailStat icon={Network} label="roles" tone="text-chart-3" value={Object.keys(node.role_buckets || {}).length} />
        </div>
      </details>
    </DetailShell>
  );
}

function RoleLegend({ roles }) {
  return (
    <div className="border-t border-border bg-background/70 px-3 py-2">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <p className="shrink-0 text-[11px] font-medium text-muted-foreground">
          Role colors
        </p>
        <div className="flex flex-wrap gap-1.5">
          {roles.map((role) => (
            <span
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/30 px-1.5 py-0.5 text-[11px] text-muted-foreground"
              key={role}
            >
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: ROLE_COLORS[role] || ROLE_COLORS.other }}
              />
              {formatRoleLabel(role)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ConnectionsGraph({
  albumConnection,
  focusNodeId,
  graph,
  isUpdating = false,
  onFocusNode,
  onInspectContributor,
  onOpenAlbum,
}) {
  const model = useMemo(
    () => withPositions(buildConnectionGraphModel(graph), albumConnection),
    [albumConnection, graph]
  );
  const [selectedState, setSelectedState] = useState({
    id: null,
    selectionScope: null,
  });
  const [previewNodeId, setPreviewNodeId] = useState(null);
  const nodeIds = useMemo(() => model.nodes.map((node) => node.id), [model.nodes]);
  const currentSelectionScope = albumConnection
    ? `connection:${albumConnection.album_a?.album_id || "a"}:${albumConnection.album_b?.album_id || "b"}`
    : focusNodeId || "default";
  const effectiveSelectedId = resolveEffectiveSelectedId({
    currentSelectionScope,
    focusNodeId,
    nodeIds,
    selectedId: selectedState.id,
    selectedSelectionScope: selectedState.selectionScope,
  });

  const selectGraphNode = (nodeId) => {
    setSelectedState({
      id: nodeId,
      selectionScope: currentSelectionScope,
    });
  };

  const activeIds = relatedIds(effectiveSelectedId, model.links);
  const activeLinks = selectedLinks(effectiveSelectedId, model.links);
  const previewNode = model.nodes.find((node) => node.id === previewNodeId) || null;
  const effectivePreviewNodeId = previewNode ? previewNodeId : null;
  const previewState = previewGraphState({
    links: model.links,
    previewNodeId: effectivePreviewNodeId,
    selectedNodeId: effectiveSelectedId,
  });
  const selectedNode = model.nodes.find((node) => node.id === effectiveSelectedId) || null;
  const startingNodes = rankStartingNodes(model);
  const startingIds = new Set(startingNodes.map((node) => node.id));
  const pathRoles = pathNodeRoles(albumConnection);
  const hasPathState = Boolean(albumConnection);
  const connectedNodes = selectedNode
    ? model.nodes.filter((node) => activeIds.has(node.id) && node.id !== selectedNode.id)
    : [];
  const title = graphTitle({ albumConnection, selectedNode });
  const roles = Array.from(new Set(model.links.map((link) => link.role))).sort();
  const visibleContributorCount = model.contributors.length;

  if (model.nodes.length === 0 && !albumConnection) return null;

  return (
    <Card className="rounded-lg">
      <CardHeader className="gap-3">
        <div>
          <CardTitle className="text-2xl font-semibold tracking-tight">
            {title}
          </CardTitle>
          <CardDescription className="max-w-3xl leading-6">
            {selectedNode || albumConnection ? (
              <span className="mt-1 block">
                This is a curated slice of recurring contributors and representative albums, not every credit in your library. Select any node and
                <strong>Explore from here</strong>
                &nbsp;to rebuild the view around it.
              </span>
            ) : null}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,320px)]">
        <div
          aria-busy={isUpdating}
          className="relative overflow-hidden rounded-lg border border-border bg-muted/30"
        >
          <svg
            aria-label="Interactive album credit connections map"
            className="block h-[360px] w-full md:h-[520px]"
            data-testid="connections-graph"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`}
          >
            <rect fill="transparent" height={GRAPH_HEIGHT} width={GRAPH_WIDTH} />
            {model.links.map((link) => {
              const source = model.nodes.find((node) => node.id === link.source);
              const target = model.nodes.find((node) => node.id === link.target);
              const isPathLink = pathRoles.has(link.source) && pathRoles.has(link.target);
              const active = effectivePreviewNodeId
                ? previewState.emphasizedLinks.has(link)
                : effectiveSelectedId
                  ? activeLinks.includes(link)
                : hasPathState
                  ? isPathLink
                  : startingIds.has(link.source) || startingIds.has(link.target);
              if (!source || !target) return null;
              return (
                <line
                  key={link.id}
                  className="transition-all duration-200 ease-out motion-reduce:transition-none"
                  opacity={isPathLink ? 0.96 : active ? 0.76 : effectivePreviewNodeId ? 0.025 : 0.045}
                  stroke={ROLE_COLORS[link.role] || ROLE_COLORS.other}
                  strokeLinecap="round"
                  strokeWidth={isPathLink ? 4.4 : active ? 2.4 : 1}
                  x1={source.x}
                  x2={target.x}
                  y1={source.y}
                  y2={target.y}
                />
              );
            })}
            {model.nodes.map((node) => {
              const selected = node.id === selectedNode?.id;
              const suggested = startingIds.has(node.id);
              const pathRole = pathRoles.get(node.id);
              const active = effectiveSelectedId
                ? activeIds.has(node.id)
                : hasPathState
                  ? pathRoles.has(node.id)
                  : suggested;
              const labeled = Boolean(pathRole)
                || Boolean(selected && node.type === "contributor")
                || Boolean(effectiveSelectedId && active && node.type === "contributor")
                || Boolean(node.type === "contributor" && visibleContributorCount <= 10);
              return (
                <GraphNode
                  active={active}
                  dimmed={effectivePreviewNodeId
                    ? !previewState.emphasizedIds.has(node.id)
                    : effectiveSelectedId ? !active : hasPathState ? !pathRoles.has(node.id) : !suggested}
                  key={node.id}
                  labeled={labeled}
                  node={node}
                  onPreviewNode={setPreviewNodeId}
                  onSelect={selectGraphNode}
                  pathRole={pathRole}
                  previewed={node.id === effectivePreviewNodeId}
                  previewRelated={previewState.previewIds.has(node.id)}
                  selected={selected}
                  suggested={suggested}
                />
              );
            })}
            <GraphPreview node={previewNode} />
          </svg>
          {roles.length > 0 && <RoleLegend roles={roles} />}
          {isUpdating && (
            <div
              aria-live="polite"
              className="absolute inset-0 z-10 flex cursor-wait items-start justify-end bg-background/20 p-3 backdrop-blur-[1px]"
              role="status"
            >
              <span className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/95 px-3 py-1.5 text-xs font-medium text-foreground shadow-sm">
                <LoaderCircle className="size-3.5 animate-spin text-primary" />
                Updating graph…
              </span>
            </div>
          )}
        </div>
        <GraphDetail
          albumConnection={albumConnection}
          connectedNodes={connectedNodes}
          links={activeLinks}
          node={selectedNode}
          onFocusNode={onFocusNode}
          onInspectContributor={onInspectContributor}
          onOpenAlbum={onOpenAlbum}
          onSelectNode={selectGraphNode}
          startingNodes={startingNodes}
        />
      </CardContent>
    </Card>
  );
}
