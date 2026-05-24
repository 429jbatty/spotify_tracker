import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { updateAlbumUserFeedback } from "../services/albumApi";

const RATING_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

function RatingButton({ active, disabled, children, onClick }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-md border text-sm font-medium transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
        disabled && "cursor-not-allowed opacity-60"
      )}
    >
      {children}
    </button>
  );
}

function AlbumUserFeedbackForm({ album, onAlbumUpdated, onDataChanged }) {
  const { toast } = useToast();
  const [rating, setRating] = useState(album.rating ?? null);
  const [notes, setNotes] = useState(album.notes ?? "");
  const [saveState, setSaveState] = useState("idle");
  const notesTimeoutRef = useRef(null);

  useEffect(() => {
    return () => {
      if (notesTimeoutRef.current) {
        window.clearTimeout(notesTimeoutRef.current);
      }
    };
  }, []);

  const saveFeedback = useCallback(async (payload, successMessage = null) => {
    setSaveState("saving");
    try {
      const updatedAlbum = await updateAlbumUserFeedback(album.id, payload);
      onAlbumUpdated?.(updatedAlbum);
      await onDataChanged?.();
      setSaveState("saved");
      if (successMessage) {
        toast({
          title: "Saved",
          description: successMessage,
        });
      }
    } catch (error) {
      setSaveState("error");
      toast({
        title: "Could not save feedback",
        description: error.message || "An error occurred while saving your feedback.",
        variant: "destructive",
      });
    }
  }, [album.id, onAlbumUpdated, onDataChanged, toast]);

  useEffect(() => {
    if (notes === (album.notes ?? "")) return undefined;

    if (notesTimeoutRef.current) {
      window.clearTimeout(notesTimeoutRef.current);
    }

    notesTimeoutRef.current = window.setTimeout(() => {
      saveFeedback(
        {
          rating,
          notes,
        },
        null
      );
    }, 750);

    return () => {
      if (notesTimeoutRef.current) {
        window.clearTimeout(notesTimeoutRef.current);
      }
    };
  }, [album.notes, notes, rating, saveFeedback]);

  const handleNotesChange = (event) => {
    const nextNotes = event.target.value;
    setNotes(nextNotes);
    setSaveState(nextNotes === (album.notes ?? "") ? "idle" : "pending");
  };

  const handleRatingClick = (value) => {
    const nextRating = rating === value ? null : value;
    setRating(nextRating);

    if (notesTimeoutRef.current) {
      window.clearTimeout(notesTimeoutRef.current);
      notesTimeoutRef.current = null;
    }

    saveFeedback(
      {
        rating: nextRating,
        notes,
      },
      "Your rating was updated."
    );
  };

  const saveStatusText =
    saveState === "saving"
      ? "Saving..."
      : saveState === "saved"
        ? "Saved"
        : saveState === "error"
          ? "Could not save"
          : saveState === "pending"
            ? "Unsaved changes"
            : null;

  return (
    <section className="space-y-4 border-t pt-4">
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-muted-foreground">Your Rating</h3>
          {rating !== null && (
            <button
              type="button"
              onClick={() => handleRatingClick(rating)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Clear
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {RATING_OPTIONS.map((value) => (
            <RatingButton
              key={value}
              active={rating === value}
              disabled={saveState === "saving"}
              onClick={() => handleRatingClick(value)}
            >
              {value}
            </RatingButton>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-medium text-muted-foreground">Notes</h3>
        <textarea
          value={notes}
          onChange={handleNotesChange}
          rows={5}
          placeholder="Write a few thoughts about this album..."
          className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />
      </div>

      {saveStatusText ? (
        <div className="text-right text-xs text-muted-foreground">{saveStatusText}</div>
      ) : null}
    </section>
  );
}

function AlbumUserFeedback({ album, onAlbumUpdated, onDataChanged }) {
  return (
    <AlbumUserFeedbackForm
      key={`${album.id}:${album.rating ?? ""}:${album.notes ?? ""}`}
      album={album}
      onAlbumUpdated={onAlbumUpdated}
      onDataChanged={onDataChanged}
    />
  );
}

export default AlbumUserFeedback;
