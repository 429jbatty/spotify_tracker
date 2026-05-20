import { cn } from "@/lib/utils";

function ratingBadgeClasses(rating) {
  if (rating >= 9) return "border-emerald-500/40 bg-emerald-500/15 text-emerald-700";
  if (rating >= 7) return "border-sky-500/40 bg-sky-500/15 text-sky-700";
  if (rating >= 5) return "border-amber-500/40 bg-amber-500/15 text-amber-700";
  return "border-rose-500/40 bg-rose-500/15 text-rose-700";
}

function AlbumRatingBadge({ rating, compact = false, className }) {
  if (!rating) return null;

  return (
    <div
      className={cn(
        "rounded-full border font-semibold shadow-sm",
        ratingBadgeClasses(rating),
        compact ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm",
        className
      )}
    >
      {rating}/10
    </div>
  );
}

export default AlbumRatingBadge;
