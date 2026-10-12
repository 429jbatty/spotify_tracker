import { useEffect, useState } from "react";

import { fetchPublicRecentListens } from "@/services/albumApi";
import ResponsiveAlbumImage from "./ResponsiveAlbumImage";

function PublicRecentListens() {
  const [listens, setListens] = useState([]);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let cancelled = false;

    fetchPublicRecentListens(5)
      .then((payload) => {
        if (cancelled) return;
        setListens(payload);
        setStatus("ready");
      })
      .catch((error) => {
        if (cancelled) return;
        console.error(error);
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") {
    return (
      <section className="rounded-lg border border-border/70 bg-card p-5 shadow-sm">
        <h2 className="text-2xl font-semibold tracking-tight text-foreground">
          What people have been listening to
        </h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => (
            <div
              key={index}
              className="aspect-[3/4] animate-pulse rounded-lg border border-border/70 bg-muted"
            />
          ))}
        </div>
      </section>
    );
  }

  if (status === "error") return null;

  return (
    <section className="rounded-lg border border-border/70 bg-card p-5 shadow-sm">
      <h2 className="text-2xl font-semibold tracking-tight text-foreground">
        What people have been listening to
      </h2>
      {listens.length > 0 ? (
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {listens.map((listen) => (
            <RecentListenCard key={listen.listen_id} listen={listen} />
          ))}
        </div>
      ) : (
        <div className="mt-5 rounded-lg border border-dashed border-border/70 bg-background/70 p-5 text-sm text-muted-foreground">
          Recent listens will appear after albums are added.
        </div>
      )}
    </section>
  );
}

function RecentListenCard({ listen }) {
  const activityText = `${formatListenDate(listen.listened_at)}, ${listen.listener_display_name} listened to:`;

  return (
    <article className="overflow-hidden rounded-lg border border-border/70 bg-background shadow-sm">
      <div className="min-h-14 border-b border-border/70 px-3 py-3">
        <p className="text-sm font-medium leading-snug text-foreground">
          {activityText}
        </p>
      </div>
      <div className="aspect-square overflow-hidden bg-muted">
        <ResponsiveAlbumImage
          src={listen.image_url}
          alt={listen.name}
          sizes="(max-width: 640px) 100vw, 320px"
          className="h-full w-full object-cover"
        />
      </div>
      <div className="space-y-1 p-3">
        <h3 className="line-clamp-2 text-sm font-medium leading-snug text-foreground">
          {listen.name}
        </h3>
        <p className="line-clamp-1 text-xs text-muted-foreground">{listen.artist}</p>
      </div>
    </article>
  );
}

function formatListenDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently";

  const today = startOfLocalDay(new Date());
  const listenedDay = startOfLocalDay(date);
  const dayDifference = Math.round((today - listenedDay) / 86400000);

  if (dayDifference === 0) return "Today";
  if (dayDifference === 1) return "Yesterday";

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date);
}

function startOfLocalDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export default PublicRecentListens;
