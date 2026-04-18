import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { ChevronDownIcon } from "lucide-react";

function TrackCredits({ credits }) {
  if (!credits || credits.length === 0) return null;

  const grouped = {};
  for (const [name, role, detail] of credits) {
    const roleDetail = detail ? `${role}, ${detail}` : role;
    if (!grouped[name]) grouped[name] = [];
    grouped[name].push(roleDetail);
  }

  return (
    <div className="mt-2 ml-10 space-y-1">
      {Object.entries(grouped).map(([name, roles]) => (
        <div key={name} className="text-xs text-muted-foreground">
          <span className="font-medium">{name}</span>
          <span> — {roles.join(", ")}</span>
        </div>
      ))}
    </div>
  );
}

function TracklistModal({ album }) {
  const tracklist = album.tracklist || [];

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          className="
            w-full mt-4
            rounded-lg border border-border
            bg-muted/40 hover:bg-muted
            text-sm font-semibold
            py-2 transition-colors
          "
        >
          Tracklist
        </button>
      </DialogTrigger>

      <DialogContent className="max-w-2xl max-h-[80vh]">

        <DialogHeader>
          <DialogTitle className="text-lg font-bold">
            {album.name}
          </DialogTitle>

          <p className="text-sm text-muted-foreground">
            {album.artist}
          </p>
        </DialogHeader>

        <div className="max-h-[60vh] overflow-y-auto pr-2">

          <Accordion type="multiple" className="w-full space-y-2">
            {tracklist.map((track) => {
              const hasCredits = track.credits && track.credits.length > 0;

              return (
                <AccordionItem
                  key={track.recording_mbid}
                  value={track.recording_mbid}
                  className="border border-border rounded-lg px-3"
                >
                  <AccordionTrigger className="hover:no-underline py-3 text-sm">
                    <div className="flex gap-4 items-center w-full">
                      <span className="w-6 text-muted-foreground font-mono">
                        {track.position}
                      </span>
                      <span className="flex-1 text-left text-foreground">
                        {track.title}
                      </span>
                      {hasCredits && (
                        <ChevronDownIcon className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>
                  </AccordionTrigger>

                  {hasCredits && (
                    <AccordionContent className="pb-3">
                      <TrackCredits credits={track.credits} />
                    </AccordionContent>
                  )}
                </AccordionItem>
              );
            })}
          </Accordion>

        </div>
      </DialogContent>
    </Dialog>
  );
}

export default TracklistModal;