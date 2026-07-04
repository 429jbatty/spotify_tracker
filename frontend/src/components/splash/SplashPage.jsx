import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  CalendarClock,
  Disc3,
  History,
  Library,
  Music2,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { fetchSplashData } from "@/services/albumApi";

const TRACKED_FEATURES = [
  {
    title: "Discoveries",
    description: "Find what newly entered your rotation.",
    icon: Sparkles,
  },
  {
    title: "Replays",
    description: "See which albums actually stuck.",
    icon: RefreshCw,
  },
  {
    title: "Trends",
    description: "Watch taste change over time.",
    icon: BarChart3,
  },
  {
    title: "Release Eras",
    description: "Map your taste by decade and year.",
    icon: CalendarClock,
  },
  {
    title: "Credits",
    description: "Trace producers, musicians, and collaborators.",
    icon: Music2,
  },
  {
    title: "Favorites",
    description: "Surface the albums you keep returning to.",
    icon: History,
  },
];

const SAMPLE_COVERS = [
  "linear-gradient(135deg, oklch(0.78 0.14 70), oklch(0.45 0.11 35))",
  "linear-gradient(135deg, oklch(0.72 0.09 210), oklch(0.36 0.06 250))",
  "linear-gradient(135deg, oklch(0.74 0.11 150), oklch(0.42 0.08 170))",
  "linear-gradient(135deg, oklch(0.82 0.08 20), oklch(0.52 0.14 5))",
  "linear-gradient(135deg, oklch(0.8 0.1 95), oklch(0.58 0.13 80))",
  "linear-gradient(135deg, oklch(0.68 0.07 290), oklch(0.35 0.08 315))",
];

const EMPTY_ARRAY = [];
const EMPTY_OBJECT = {};

function SplashPage({ onOpenProfile }) {
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    fetchSplashData({ signal: controller.signal })
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        setStatus("ready");
      })
      .catch((error) => {
        if (cancelled || controller.signal.aborted) return;
        if (error?.name !== "TypeError") {
          console.error(error);
        }
        setStatus("error");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  const featuredUsers = payload?.featured_users || EMPTY_ARRAY;
  const recentActivity = payload?.recent_activity || EMPTY_ARRAY;
  const heroStats = payload?.hero_stats || EMPTY_OBJECT;
  const previewCovers = useMemo(
    () => collectPreviewCovers(featuredUsers, recentActivity),
    [featuredUsers, recentActivity],
  );

  const handleExplore = () => {
    const target = document.getElementById("profiles");
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleAbout = () => {
    const target = document.getElementById("tracks");
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <main className="min-h-screen bg-background text-foreground">
      <SplashHeader onBrowse={handleExplore} onAbout={handleAbout} />
      <div className="mx-auto flex max-w-7xl flex-col gap-14 px-5 pb-14 pt-4 sm:px-6 lg:px-8">
        <section className="grid min-h-[450px] items-center gap-8 lg:min-h-[520px] lg:grid-cols-[minmax(0,0.95fr)_minmax(440px,1fr)]">
          <SplashHero onExplore={handleExplore} />
          <HeroAlbumPreview
            covers={previewCovers}
            heroStats={heroStats}
            featuredUsers={featuredUsers}
            recentActivity={recentActivity}
            status={status}
          />
        </section>

        <FeaturedProfiles
          users={featuredUsers}
          totalUsers={featuredUsers.length}
          status={status}
          onBrowse={handleExplore}
          onOpenProfile={onOpenProfile}
        />

        <RecentActivity
          activity={recentActivity}
          status={status}
          onOpenProfile={onOpenProfile}
        />

        <TrackedFeatures />
      </div>
    </main>
  );
}

function SplashHeader({ onBrowse, onAbout }) {
  return (
    <header className="sticky top-0 z-20 border-b border-border/70 bg-background/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3" aria-label="Albumary home">
          <span className="flex size-10 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
            <Library className="size-5" />
          </span>
          <span className="text-lg font-semibold tracking-tight">Albumary</span>
        </div>
        <nav className="flex items-center gap-4 text-sm font-medium text-muted-foreground">
          <button
            type="button"
            onClick={onBrowse}
            className="transition-colors hover:text-foreground"
          >
            Browse Profiles
          </button>
          <button
            type="button"
            onClick={onAbout}
            className="transition-colors hover:text-foreground"
          >
            About
          </button>
        </nav>
      </div>
    </header>
  );
}

function SplashHero({ onExplore }) {
  return (
    <div className="flex flex-col gap-7">
      <div className="flex flex-col gap-5">
        <h1 className="max-w-2xl text-5xl font-semibold leading-[1.02] tracking-tight text-foreground sm:text-6xl lg:text-7xl">
          Your music taste, mapped over time.
        </h1>
        <p className="max-w-xl text-lg leading-8 text-muted-foreground">
          Albumary turns album listening into public profiles of discoveries,
          returns, eras, artists, and how taste changes over time.
        </p>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button type="button" onClick={onExplore} className="sm:w-auto">
          <Search data-icon="inline-start" />
          Explore profiles
        </Button>
      </div>
    </div>
  );
}

function HeroAlbumPreview({ covers, heroStats, featuredUsers, recentActivity, status }) {
  const displayCovers = covers.length ? covers : [];
  const profileUser = heroProfileUser(featuredUsers);
  const replayMoment = heroReplayMoment(featuredUsers, recentActivity);
  const profileName = profileDisplayName(profileUser);
  const profileTitle = profileName
    ? `${formatPossessiveName(profileName)} Albumary`
    : "Albumary profile";
  const profileSummary = profileUser
    ? formatAlbumListenSummary(profileUser)
    : "Albums tracked over time";
  const eraValue = profileUser?.most_listened_era?.label || heroStats.top_era || "Listening";

  return (
    <div className="relative flex items-center justify-center overflow-hidden rounded-lg sm:overflow-visible lg:min-h-[460px]">
      <div className="absolute inset-0 rounded-lg bg-[linear-gradient(135deg,rgba(236,201,75,0.18),rgba(114,160,193,0.12)_46%,rgba(255,255,255,0))]" />
      <div className="relative grid w-full max-w-xl grid-cols-1 gap-4 sm:grid-cols-[1fr_0.9fr]">
        <div className="grid grid-cols-3 gap-2 self-center sm:grid-cols-2 sm:gap-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <CoverTile
              key={index}
              src={displayCovers[index]}
              index={index}
              loading={status === "loading"}
              className={index % 3 === 0 ? "translate-y-5" : ""}
            />
          ))}
        </div>
        <div className="flex flex-col justify-center gap-3">
          <div className="rounded-lg border border-border/80 bg-background/88 p-4 shadow-sm backdrop-blur">
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
              Profile preview
            </p>
            <p className="mt-2 text-xl font-semibold tracking-tight text-foreground">
              {profileTitle}
            </p>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">
              {profileSummary}
            </p>
          </div>
          <HeroReplayMoment moment={replayMoment} />
          <HeroStat
            label="Discovery Rate"
            value={formatPercent(heroStats.discovery_rate) || "Fresh"}
          />
          <HeroStat label="Most-listened Era" value={eraValue} />
        </div>
      </div>
    </div>
  );
}

function HeroReplayMoment({ moment }) {
  const Icon = moment?.type === "activity" ? History : RefreshCw;

  return (
    <div className="rounded-lg border border-primary/25 bg-background/92 p-4 shadow-md backdrop-blur">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
        <Icon className="size-4 text-primary" />
        Return moment
      </div>
      <p className="mt-3 text-2xl font-semibold leading-tight tracking-tight text-foreground">
        {moment?.title || "Returned albums surface here"}
      </p>
      {moment?.subtitle && (
        <p className="mt-2 text-sm leading-5 text-muted-foreground">
          {moment.subtitle}
        </p>
      )}
    </div>
  );
}

function HeroStat({ label, value }) {
  return (
    <div className="rounded-lg border border-border/80 bg-background/88 p-4 shadow-sm backdrop-blur">
      <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 text-3xl font-semibold tracking-tight text-foreground">
        {value}
      </p>
    </div>
  );
}

function FeaturedProfiles({ users, totalUsers, status, onBrowse, onOpenProfile }) {
  return (
    <section id="profiles" className="scroll-mt-24">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <SectionHeading
          title="Explore listening profiles"
          description="A compact preview of public listening libraries."
        />
        {totalUsers > 0 && (
          <button
            type="button"
            onClick={onBrowse}
            className="text-left text-sm font-medium text-muted-foreground transition-colors hover:text-foreground sm:text-right"
          >
            Showing {totalUsers} {totalUsers === 1 ? "profile" : "profiles"}
          </button>
        )}
      </div>
      {status === "loading" ? (
        <div className="mt-5 grid gap-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <ProfileSkeleton key={index} />
          ))}
        </div>
      ) : users.length > 0 ? (
        <div className="mt-5 grid gap-3">
          {users.map((user) => (
            <ProfileRow
              key={user.slug}
              user={user}
              onOpenProfile={onOpenProfile}
            />
          ))}
        </div>
      ) : (
        <EmptyPanel message="Profiles will appear here after listeners are added." />
      )}
    </section>
  );
}

function ProfileRow({ user, onOpenProfile }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const expandedStateClass = isExpanded
    ? "md:mt-2 md:max-h-[164px] md:opacity-100"
    : "md:max-h-0 md:opacity-0";

  return (
    <button
      type="button"
      data-testid="profile-row"
      onFocus={() => setIsExpanded(true)}
      onBlur={() => setIsExpanded(false)}
      onMouseEnter={() => setIsExpanded(true)}
      onMouseLeave={() => setIsExpanded(false)}
      onClick={() => onOpenProfile(user.slug)}
      className="group cursor-pointer rounded-lg border border-border/80 bg-card p-3 text-left shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-primary/35 hover:bg-primary/5 hover:shadow-md focus:-translate-y-0.5 focus:border-primary/35 focus:bg-primary/5 focus:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
    >
      <div className="grid gap-3 md:grid-cols-[112px_minmax(140px,1fr)_minmax(260px,auto)_auto_auto] md:items-center">
        <CoverStack covers={user.recent_album_covers} variant="compact" />
        <div className="min-w-0 md:pr-2">
          <h3 className="truncate text-lg font-semibold tracking-tight text-foreground">
            {profileDisplayName(user)}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground md:hidden">
            {formatAlbumListenSummary(user)}
          </p>
        </div>
        <p className="hidden text-sm text-muted-foreground md:block">
          {formatAlbumListenSummary(user)}
        </p>
        <span className="hidden text-sm text-muted-foreground md:block">
          {formatUpdated(user.last_updated)}
        </span>
        <span className="rounded-md border border-border/70 px-2 py-1 text-xs font-medium text-muted-foreground transition group-hover:border-primary/25 group-hover:text-foreground group-focus-visible:border-primary/25 group-focus-visible:text-foreground">
          Open →
        </span>
      </div>
      <div
        data-testid="profile-row-expanded"
        className={`grid overflow-hidden transition-all duration-200 ${expandedStateClass}`}
      >
        <div className="mt-2 grid gap-2 border-t border-border/70 pt-2 md:mt-0 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
          <div className="grid min-w-0 gap-x-4 gap-y-2 text-sm sm:grid-cols-2 md:grid-cols-3">
            <ProfileMetric
              label="Top artist"
              value={user.top_artist || "Not enough data"}
              secondary={formatListenCount(user.top_artist_listen_count)}
            />
            <ProfileMetric
              label="Top album"
              value={user.top_album?.title || "Not enough data"}
              secondary={user.top_album?.artist}
            />
            <ProfileMetric
              label="Discovery rate"
              value={formatPercent(user.discovery_rate) || "Not enough data"}
              secondary="First-time listens"
            />
            <ProfileMetric
              label="Most-listened era"
              value={user.most_listened_era?.label || "Not enough data"}
              secondary={formatListenCount(user.most_listened_era?.listen_count)}
            />
            <ProfileMetric
              label="Most replayed recently"
              value={user.most_replayed_recently?.title || "No recent replays"}
              secondary={formatRecentReplay(user.most_replayed_recently)}
            />
          </div>
          <span className="hidden rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground md:inline-flex">
            Open profile →
          </span>
        </div>
      </div>
    </button>
  );
}

function ProfileMetric({ label, value, secondary }) {
  return (
    <p className="grid min-w-0 gap-0.5">
      <span className="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
        {label}
      </span>
      <span className="truncate font-medium text-foreground">{value}</span>
      {secondary && (
        <span className="truncate text-xs text-muted-foreground">{secondary}</span>
      )}
    </p>
  );
}

function CoverStack({ covers, variant = "expanded" }) {
  const realCovers = covers.filter(Boolean);
  const maxVisible = variant === "compact" ? 3 : 4;
  const visibleCovers = realCovers.length > maxVisible ? realCovers.slice(0, maxVisible) : realCovers;
  const hiddenCount = Math.max(0, realCovers.length - visibleCovers.length);
  const containerClass =
    variant === "compact"
      ? "h-14 w-28 p-2"
      : "h-24 w-full p-3 md:w-36";
  const tileClass = variant === "compact" ? "size-11" : "";

  if (realCovers.length === 0) {
    return (
      <div className={`flex items-end overflow-hidden rounded-md border border-border/70 bg-muted ${containerClass}`}>
        <CoverTile index={0} className={`opacity-70 ${tileClass}`} small />
      </div>
    );
  }

  return (
    <div className={`flex items-end overflow-hidden rounded-md border border-border/70 bg-muted ${containerClass}`}>
      {visibleCovers.map((cover, index) => (
        <CoverTile
          key={index}
          src={cover}
          index={index}
          className={`-ml-3 first:ml-0 ${tileClass}`}
          small
        />
      ))}
      {hiddenCount > 0 && (
        <div className={`-ml-3 flex items-center justify-center rounded-md border border-border/80 bg-background/85 text-sm font-semibold text-muted-foreground shadow-sm ${variant === "compact" ? "size-11" : "size-16 sm:size-20"}`}>
          +{hiddenCount}
        </div>
      )}
    </div>
  );
}

function RecentActivity({ activity, status, onOpenProfile }) {
  return (
    <section>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <SectionHeading title="Recently on Albumary" />
        {activity.length > 6 && (
          <span className="text-sm font-medium text-muted-foreground">
            Latest {Math.min(activity.length, 6)}
          </span>
        )}
      </div>
      <div className="mt-5 overflow-hidden rounded-lg border border-border/80 bg-card shadow-sm">
        {status === "loading" ? (
          <div className="grid">
            {Array.from({ length: 5 }).map((_, index) => (
              <div
                key={index}
                className="h-16 border-b border-border/70 bg-muted last:border-b-0"
              />
            ))}
          </div>
        ) : activity.length > 0 ? (
          <div className="divide-y divide-border/70">
            {activity.slice(0, 5).map((item) => (
              <ActivityItem
                key={`${item.timestamp}-${item.text}`}
                item={item}
                onOpenProfile={onOpenProfile}
              />
            ))}
          </div>
        ) : (
          <EmptyPanel message="Recent album activity will appear here." compact />
        )}
      </div>
    </section>
  );
}

function ActivityItem({ item, onOpenProfile }) {
  const userSlug = item.profile_url?.split("/").filter(Boolean)[0];

  const handleClick = (event) => {
    if (!userSlug) return;
    event.preventDefault();
    onOpenProfile(userSlug);
  };

  return (
    <a
      href={item.profile_url}
      onClick={handleClick}
      className="grid grid-cols-[48px_minmax(0,1fr)] items-center gap-3 px-4 py-2.5 transition-colors hover:bg-muted/50"
    >
      <CoverTile src={item.album_cover_url} index={0} small square />
      <div className="min-w-0">
        <p className="line-clamp-2 text-sm leading-6 text-foreground">
          <span className="font-semibold">{activityDisplayName(item)}</span>{" "}
          {activityActionText(item)}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {formatActivityTimestamp(item.timestamp)}
        </p>
      </div>
    </a>
  );
}

function TrackedFeatures() {
  return (
    <section id="tracks" className="scroll-mt-24">
      <SectionHeading title="What Albumary tracks" compact />
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {TRACKED_FEATURES.map((feature) => {
          const Icon = feature.icon;
          return (
            <article
              key={feature.title}
              className="grid grid-cols-[28px_minmax(0,1fr)] gap-3 rounded-md border border-border/80 bg-card px-3 py-2.5 shadow-sm"
            >
              <div className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Icon className="size-4" />
              </div>
              <div className="min-w-0">
                <h3 className="text-sm font-semibold leading-5 tracking-tight text-foreground">
                  {feature.title}
                </h3>
                <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
                  {feature.description}
                </p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function SectionHeading({ title, description, compact = false }) {
  return (
    <div className={`flex flex-col ${compact ? "gap-1" : "gap-2"}`}>
      <h2 className={`${compact ? "text-xl" : "text-2xl"} font-semibold tracking-tight text-foreground`}>
        {title}
      </h2>
      {description && (
        <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
          {description}
        </p>
      )}
    </div>
  );
}

function ProfileSkeleton() {
  return (
    <div className="rounded-lg border border-border/80 bg-card p-4 shadow-sm">
      <div className="h-28 rounded-md bg-muted" />
      <div className="mt-4 h-6 w-32 rounded bg-muted" />
      <div className="mt-3 h-4 w-48 rounded bg-muted" />
      <div className="mt-5 grid gap-2">
        <div className="h-4 rounded bg-muted" />
        <div className="h-4 rounded bg-muted" />
        <div className="h-4 w-28 rounded bg-muted" />
      </div>
    </div>
  );
}

function EmptyPanel({ message, compact = false }) {
  return (
    <div
      className={`mt-5 rounded-lg border border-dashed border-border/80 bg-card text-sm text-muted-foreground ${
        compact ? "p-4" : "p-6"
      }`}
    >
      {message}
    </div>
  );
}

function CoverTile({ src, index, className = "", loading = false, small = false, square = false }) {
  const sizeClass = square ? "size-12" : small ? "size-16 sm:size-20" : "aspect-square w-full";
  const content = src ? (
    <img
      src={src}
      alt=""
      className="h-full w-full object-cover"
      loading="lazy"
      onError={(event) => {
        event.currentTarget.style.display = "none";
      }}
    />
  ) : (
    <div
      className="h-full w-full"
      style={{ background: SAMPLE_COVERS[index % SAMPLE_COVERS.length] }}
    >
      <div className="flex h-full items-end p-2">
        <Disc3 className="size-5 text-white/80" />
      </div>
    </div>
  );

  return (
    <div
      className={`overflow-hidden rounded-md border border-white/70 bg-muted shadow-sm ${sizeClass} ${loading ? "animate-pulse" : ""} ${className}`}
    >
      {content}
    </div>
  );
}

function collectPreviewCovers(users, activity) {
  const covers = [];
  users.forEach((user) => {
    user.recent_album_covers?.forEach((cover) => covers.push(cover));
  });
  activity.forEach((item) => {
    if (item.album_cover_url) covers.push(item.album_cover_url);
  });
  return [...new Set(covers)].slice(0, 6);
}

function heroProfileUser(featuredUsers) {
  return featuredUsers?.[0] || null;
}

function heroReplayMoment(featuredUsers, recentActivity) {
  const primaryUserReplay = featuredUsers?.[0]?.most_replayed_recently;
  if (primaryUserReplay) {
    return {
      type: "metric",
      title: `Returned to “${primaryUserReplay.title}”`,
      subtitle: `${primaryUserReplay.artist} · replayed in the last ${primaryUserReplay.window_days} days`,
    };
  }

  const replayActivity = recentActivity?.find((item) => item.type === "replay");
  if (replayActivity) {
    return {
      type: "activity",
      title: replayActivity.text?.replace(/\.$/, "") || `Returned to “${replayActivity.album_title}”`,
      subtitle: `${replayActivity.artist_name} · recent profile activity`,
    };
  }

  return null;
}

function formatPossessiveName(name) {
  const trimmed = String(name || "").trim();
  if (!trimmed) return "";
  return trimmed.endsWith("s") ? `${trimmed}’` : `${trimmed}’s`;
}

function formatPercent(value) {
  if (typeof value !== "number") return null;
  return `${Math.round(value * 100)}%`;
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value || 0);
}

function formatListenCount(value) {
  if (typeof value !== "number") return null;
  return `${formatNumber(value)} ${value === 1 ? "listen" : "listens"}`;
}

function formatRecentReplay(replay) {
  if (!replay) return null;
  const replayCount = `${formatNumber(replay.replay_count)} ${
    replay.replay_count === 1 ? "replay" : "replays"
  }`;
  return `${replay.artist} · ${replayCount}, ${replay.window_days} days`;
}

function formatAlbumListenSummary(user) {
  return `${formatNumber(user.total_albums)} albums tracked · ${formatNumber(user.total_listens)} listening sessions`;
}

function formatUpdated(value) {
  if (!value) return "No listens yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Updated recently";

  const today = startOfLocalDay(new Date());
  const target = startOfLocalDay(date);
  const dayDifference = Math.round((today - target) / 86400000);

  if (dayDifference === 0) return "Updated today";
  if (dayDifference === 1) return "Updated yesterday";
  if (dayDifference > 1 && dayDifference < 7) {
    return `Updated ${dayDifference} days ago`;
  }

  return `Last updated ${new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date)}`;
}

function formatActivityTimestamp(value) {
  if (!value) return "Recently";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently";

  const today = startOfLocalDay(new Date());
  const target = startOfLocalDay(date);
  const dayDifference = Math.round((today - target) / 86400000);

  if (dayDifference === 0) return "Today";
  if (dayDifference === 1) return "Yesterday";
  if (dayDifference > 1 && dayDifference < 7) return `${dayDifference} days ago`;

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date);
}

function activityActionText(item) {
  const albumText = (
    <>
      <span className="font-medium">“{item.album_title}”</span>
      <span className="text-muted-foreground"> by {item.artist_name}</span>
    </>
  );

  if (item.type === "replay") {
    const match = item.text?.match(/after (.+)\.$/);
    return (
      <>
        replayed {albumText}
        {match ? <span className="text-muted-foreground"> after {match[1]}</span> : null}
      </>
    );
  }

  return <>discovered {albumText}</>;
}

function profileDisplayName(user) {
  return user?.public_display_name || user?.display_name || "";
}

function activityDisplayName(item) {
  return item.public_user_display_name || item.user_display_name;
}

function startOfLocalDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export default SplashPage;
