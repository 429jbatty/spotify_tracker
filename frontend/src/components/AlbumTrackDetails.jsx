import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { createAlbumFilter } from "./utils/albumFilters";

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

function TrackCredits({ credits, onFilterSelect }) {
  const groupedCredits = groupCreditsByPerson(credits);
  const entries = Object.entries(groupedCredits);

  if (entries.length === 0) {
    return (
      <p className="pl-10 text-xs text-muted-foreground">
        No track credits in the current metadata.
      </p>
    );
  }

  return (
    <div className="pl-10 space-y-2">
      {entries.map(([name, roles]) => (
        <div key={name} className="text-xs leading-relaxed">
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
      ))}
    </div>
  );
}

function TrackRow({ track, index, onFilterSelect }) {
  const credits = getTrackCredits(track);
  const hasCredits = credits.length > 0;
  const value = getTrackKey(track, index);

  return (
    <AccordionItem value={value} className="border-b border-border last:border-b-0">
      <AccordionTrigger className="hover:no-underline py-3">
        <div className="grid w-full grid-cols-[2.25rem_1fr_auto] items-center gap-3 pr-2 text-left">
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
        <TrackCredits credits={credits} onFilterSelect={onFilterSelect} />
      </AccordionContent>
    </AccordionItem>
  );
}

function AlbumTrackDetails({ album, onFilterSelect }) {
  const tracklist = album.tracklist || [];

  if (tracklist.length === 0) return null;

  const tracksWithCredits = tracklist.filter(
    (track) => getTrackCredits(track).length > 0
  ).length;

  return (
    <Accordion type="single" collapsible className="w-full">
      <AccordionItem value="tracks" className="border-0">
        <AccordionTrigger className="hover:no-underline py-2 px-0">
          <div className="flex w-full items-center justify-between gap-4 pr-2 text-left">
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                Tracks and credits
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {tracklist.length} tracks, credits on {tracksWithCredits}
              </p>
            </div>
          </div>
        </AccordionTrigger>

        <AccordionContent className="pb-0">
          <Accordion type="multiple" className="rounded-lg border border-border">
            {tracklist.map((track, index) => (
              <TrackRow
                key={getTrackKey(track, index)}
                track={track}
                index={index}
                onFilterSelect={onFilterSelect}
              />
            ))}
          </Accordion>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

export default AlbumTrackDetails;
