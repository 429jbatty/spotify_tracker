function formatTrackLabel(match) {
  const title = match.trackTitle || "Untitled track";
  return match.trackPosition ? `Track ${match.trackPosition}: ${title}` : title;
}

function formatCreditMatch(match) {
  const creditParts = [match.name, match.role, match.detail].filter(Boolean);
  const creditText = creditParts.join(" - ");
  return `Credit: ${creditText} on ${formatTrackLabel(match)}`;
}

function formatAlbumMatch(match) {
  return `Matched ${match.label || match.field}: ${match.value}`;
}

function formatSearchMatch(match) {
  if (match.type === "credit") return formatCreditMatch(match);
  return formatAlbumMatch(match);
}

function AlbumSearchMatches({ matches = [], limit = 2, className = "" }) {
  if (!matches.length) return null;

  const visibleMatches = matches.slice(0, limit);
  const hiddenCount = Math.max(matches.length - visibleMatches.length, 0);

  return (
    <div className={`mt-1 flex min-w-0 flex-col gap-1 ${className}`}>
      {visibleMatches.map((match, index) => (
        <span
          key={`${match.type}-${match.field}-${match.value}-${match.trackPosition || ""}-${index}`}
          className="block min-w-0 truncate text-xs font-normal text-muted-foreground"
          title={formatSearchMatch(match)}
        >
          {formatSearchMatch(match)}
        </span>
      ))}
      {hiddenCount > 0 && (
        <span className="text-xs font-normal text-muted-foreground">
          +{hiddenCount} more
        </span>
      )}
    </div>
  );
}

export default AlbumSearchMatches;
