import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { cn } from "@/lib/utils";
import { createAlbumFilter } from "./utils/albumFilters";

function normalize(value) {
  return String(value || "").toLowerCase();
}

function getTrackCredits(track) {
  return Array.isArray(track.credits) ? track.credits : [];
}

function getTrackKey(track, index) {
  return track.recording_mbid || `${track.position || index}-${track.title || "track"}`;
}

function groupCreditsByPerson(credits) {
  const grouped = {};

  for (const credit of credits) {
    if (!Array.isArray(credit) || credit.length < 2) continue;

    const [name, role, detail] = credit;
    if (!name || !role) continue;

    const roleDetail = detail ? `${role}, ${detail}` : role;
    if (!grouped[name]) grouped[name] = new Set();
    grouped[name].add(roleDetail);
  }

  return Object.fromEntries(
    Object.entries(grouped).map(([name, roles]) => [name, Array.from(roles)])
  );
}

function creditMatchesTerm(name, roles, searchTerm) {
  const term = normalize(searchTerm).trim();
  if (!term) return false;
  return [name, ...roles].some((value) => normalize(value).includes(term));
}

function trackMatchesCreditSearch(track, searchTerm) {
  const term = normalize(searchTerm).trim();
  if (!term) return false;

  return getTrackCredits(track).some(([name, role, detail]) =>
    [name, role, detail].some((value) => normalize(value).includes(term))
  );
}

function TrackCredits({ credits, searchTerm, highlightMatches, onFilterSelect }) {
  const groupedCredits = groupCreditsByPerson(credits);
  const entries = Object.entries(groupedCredits);

  if (entries.length === 0) {
    return (
      <p className="pl-16 text-xs text-muted-foreground">
        No track credits in the current metadata.
      </p>
    );
  }

  return (
    <div className="pl-16 space-y-2">
      {entries.map(([name, roles]) => {
        const isMatch = highlightMatches && creditMatchesTerm(name, roles, searchTerm);

        return (
          <div
            key={name}
            className={cn(
              "rounded-md px-2 py-1 text-xs leading-relaxed",
              isMatch && "border border-primary/30 bg-primary/10"
            )}
          >
            {onFilterSelect ? (
              <button
                type="button"
                onClick={() =>
                  onFilterSelect(createAlbumFilter("credit", name, name))
                }
                className="font-medium text-foreground hover:underline"
              >
                {name}
              </button>
            ) : (
              <span className="font-medium text-foreground">{name}</span>
            )}
            <span className="text-muted-foreground"> - {roles.join(", ")}</span>
          </div>
        );
      })}
    </div>
  );
}

function TrackRow({ track, index, searchTerm, highlightMatches, onFilterSelect }) {
  const credits = getTrackCredits(track);
  const hasCredits = credits.length > 0;
  const value = getTrackKey(track, index);
  const isMatch = highlightMatches && trackMatchesCreditSearch(track, searchTerm);

  return (
    <AccordionItem
      value={value}
      className={cn(
        "border-b border-border last:border-b-0",
        isMatch && "bg-primary/5"
      )}
    >
      <AccordionTrigger className="hover:no-underline py-3">
        <div className="grid w-full grid-cols-[2.75rem_1fr_auto] items-center gap-3 pl-4 pr-2 text-left">
          <span className="text-xs font-mono text-muted-foreground">
            {track.position || index + 1}
          </span>
          <span className="min-w-0 text-sm font-medium text-foreground">
            {track.title || "Untitled track"}
          </span>
          <span className="rounded-md border border-border px-2 py-1 text-[11px] font-medium text-muted-foreground">
            {hasCredits ? `${credits.length} credit${credits.length === 1 ? "" : "s"}` : "No credits"}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent className="pb-4">
        <TrackCredits
          credits={credits}
          searchTerm={searchTerm}
          highlightMatches={highlightMatches}
          onFilterSelect={onFilterSelect}
        />
      </AccordionContent>
    </AccordionItem>
  );
}

function TrackDetailsSummary({ trackCount, tracksWithCredits }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground">
        Tracks and credits
      </h3>
      <p className="mt-1 text-xs text-muted-foreground">
        {trackCount} tracks, credits on {tracksWithCredits}
      </p>
    </div>
  );
}

function TrackList({
  tracklist,
  searchTerm,
  highlightMatches,
  defaultOpenValues = [],
  onFilterSelect,
  className = "",
}) {
  return (
    <Accordion
      key={searchTerm || "track-list"}
      type="multiple"
      defaultValue={defaultOpenValues}
      className={`rounded-lg border border-border ${className}`}
    >
      {tracklist.map((track, index) => (
        <TrackRow
          key={getTrackKey(track, index)}
          track={track}
          index={index}
          searchTerm={searchTerm}
          highlightMatches={highlightMatches}
          onFilterSelect={onFilterSelect}
        />
      ))}
    </Accordion>
  );
}

function AlbumTrackDetails({
  album,
  searchTerm,
  searchMatches = [],
  onFilterSelect,
  open,
  onOpenChange,
  variant = "accordion",
}) {
  const tracklist = album.tracklist || [];

  if (tracklist.length === 0) return null;

  const hasCreditSearchMatches = searchMatches.some((match) => match.type === "credit");
  const tracksWithCredits = tracklist.filter(
    (track) => getTrackCredits(track).length > 0
  ).length;
  const matchedTrackValues = hasCreditSearchMatches
    ? tracklist
        .map((track, index) =>
          trackMatchesCreditSearch(track, searchTerm) ? getTrackKey(track, index) : null
        )
        .filter(Boolean)
    : [];

  const accordionProps =
    open === undefined
      ? {}
      : {
          value: open ? "tracks" : "",
          onValueChange: (value) => onOpenChange?.(value === "tracks"),
        };

  if (variant === "panel") {
    return (
      <div className="flex min-h-full flex-col gap-4 p-6">
        <TrackDetailsSummary
          trackCount={tracklist.length}
          tracksWithCredits={tracksWithCredits}
        />
        <TrackList
          tracklist={tracklist}
          searchTerm={searchTerm}
          highlightMatches={hasCreditSearchMatches}
          defaultOpenValues={matchedTrackValues}
          onFilterSelect={onFilterSelect}
        />
      </div>
    );
  }

  return (
    <Accordion type="single" collapsible className="w-full" {...accordionProps}>
      <AccordionItem value="tracks" className="border-0">
        <AccordionTrigger className="hover:no-underline py-2 px-0">
          <div className="flex w-full items-center justify-between gap-4 pr-2 text-left">
            <TrackDetailsSummary
              trackCount={tracklist.length}
              tracksWithCredits={tracksWithCredits}
            />
          </div>
        </AccordionTrigger>

        {variant === "trigger" ? null : (
          <AccordionContent className="pb-0">
            <TrackList
              tracklist={tracklist}
              searchTerm={searchTerm}
              highlightMatches={hasCreditSearchMatches}
              defaultOpenValues={matchedTrackValues}
              onFilterSelect={onFilterSelect}
              className="lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto"
            />
          </AccordionContent>
        )}
      </AccordionItem>
    </Accordion>
  );
}

export default AlbumTrackDetails;
