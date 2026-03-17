import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

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

      <DialogContent className="max-w-lg">

        <DialogHeader>
          <DialogTitle className="text-lg font-bold">
            {album.name}
          </DialogTitle>

          <p className="text-sm text-muted-foreground">
            {album.artist}
          </p>
        </DialogHeader>

        <div className="max-h-[60vh] overflow-y-auto pr-2">

          <ol className="space-y-2 mt-4">
            {tracklist.map((track) => (
              <li
                key={track.recording_mbid}
                className="flex gap-4 text-sm border-b border-border pb-2"
              >
                <span className="w-6 text-muted-foreground">
                  {track.position}
                </span>

                <span className="flex-1 text-foreground">
                  {track.title}
                </span>
              </li>
            ))}
          </ol>

        </div>
      </DialogContent>
    </Dialog>
  );
}

export default TracklistModal;