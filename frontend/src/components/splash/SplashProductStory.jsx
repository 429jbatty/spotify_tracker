import {
  ArrowRight,
  Disc3,
  Headphones,
  Radio,
  Upload,
} from "lucide-react";

import { Button } from "@/components/ui/button";

const HISTORY_SOURCES = [
  {
    title: "Connect Spotify",
    description: "Sync new completed album listens as you keep listening.",
    icon: Headphones,
  },
  {
    title: "Import Last.fm",
    description: "Turn public scrobbles into completed album listens.",
    icon: Radio,
  },
  {
    title: "Upload Spotify history",
    description: "Bring in past listening from your Extended Streaming History ZIP.",
    icon: Upload,
  },
  {
    title: "Log an album yourself",
    description: "Add an album and its listening date yourself.",
    icon: Disc3,
  },
];

export default function SplashProductStory({
  onExplore,
  onCreateProfile,
  profileSetupIncomplete = false,
}) {
  return (
    <div className="flex flex-col gap-10">
      <section className="relative overflow-hidden rounded-2xl bg-[linear-gradient(125deg,rgba(236,201,75,0.09),rgba(255,255,255,0)_42%,rgba(114,160,193,0.08))]">
        <div className="absolute -left-24 -top-36 size-80 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute -bottom-40 right-0 size-96 rounded-full bg-[oklch(0.72_0.09_210/0.13)] blur-3xl" />
        <div className="relative grid min-h-[500px] items-center gap-8 px-6 py-8 sm:px-10 lg:grid-cols-[minmax(0,0.92fr)_minmax(460px,1fr)] lg:px-12 lg:py-10">
          <SplashHeroCopy
            onExplore={onExplore}
            onCreateProfile={onCreateProfile}
            profileSetupIncomplete={profileSetupIncomplete}
          />
          <ListeningJournalPreview />
        </div>
      </section>

      <HistorySources />
    </div>
  );
}

function SplashHeroCopy({ onExplore, onCreateProfile, profileSetupIncomplete }) {
  return (
    <div className="flex flex-col gap-7">
      <div className="flex flex-col gap-5">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
          <span className="size-1.5 rounded-full bg-primary" />
          Your personal album-listening history
        </p>
        <h1 className="max-w-2xl text-5xl font-semibold leading-[1.02] tracking-[-0.045em] text-foreground sm:text-6xl">
          Keep a history of the albums you listen to.
        </h1>
        <p className="max-w-xl text-lg leading-8 text-muted-foreground">
          Build a lasting record from Spotify, Last.fm, or albums you log yourself.
          See your first listens, returning favorites, listening eras, and how your
          taste changes over time.
        </p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        {onCreateProfile && (
          <Button type="button" size="lg" onClick={onCreateProfile}>
            {profileSetupIncomplete ? "Finish setting up your profile" : "Start your album history"}
            <ArrowRight data-icon="inline-end" />
          </Button>
        )}
        <Button type="button" size="lg" variant="outline" onClick={onExplore}>
          Explore a real profile
        </Button>
      </div>

    </div>
  );
}

function ListeningJournalPreview() {
  return (
    <div className="relative mx-auto w-full max-w-xl py-4 lg:py-6">
      <div className="absolute inset-x-6 top-0 grid grid-cols-4 gap-2 opacity-55 sm:inset-x-12">
        {[
          ["/splash-artwork/titanic-rising.jpg", "Titanic Rising by Weyes Blood"],
          ["/splash-artwork/bitches-brew.jpg", "Bitches Brew by Miles Davis"],
          ["/splash-artwork/madvillainy.jpg", "Madvillainy by Madvillain"],
          ["/splash-artwork/blonde.jpg", "Blonde by Frank Ocean"],
        ].map(([src, alt]) => (
          <img
            key={src}
            src={src}
            alt={alt}
            className="aspect-square w-full rounded-lg border border-white/70 object-cover shadow-sm"
          />
        ))}
      </div>

      <article className="relative mt-20 rounded-xl border border-border/80 bg-background/95 p-4 shadow-lg backdrop-blur sm:ml-8 sm:p-5">
        <div className="flex items-center justify-between gap-3 border-b border-border/70 pb-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Album record</p>
            <p className="mt-1 text-sm text-muted-foreground">A real history, album by album</p>
          </div>
          <span className="rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
            Example profile
          </span>
        </div>

        <div className="mt-5 grid grid-cols-[76px_minmax(0,1fr)] gap-4 sm:grid-cols-[112px_minmax(0,1fr)]">
          <img
            src="/splash-artwork/homogenic.jpg"
            alt="Homogenic by Björk"
            className="aspect-square w-full rounded-lg border border-border/70 object-cover shadow-sm"
          />
          <div className="min-w-0 self-center">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">3 listens logged</p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight text-foreground">Homogenic</h2>
            <p className="text-sm text-muted-foreground">Björk</p>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">
              First: Jun 8, 2024 · Last: Aug 15, 2026
            </p>
          </div>
        </div>

        <div className="mt-5 rounded-lg border border-border/70 bg-muted/55 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">Album notes</p>
          <blockquote className="mt-1 text-sm leading-6 text-foreground">
            “The production opens up more every time I return.”
          </blockquote>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3">
          <JournalStat label="Your album rating" value="9/10" />
          <JournalStat label="First listens this year" value="33%" />
        </div>
      </article>
    </div>
  );
}

function JournalStat({ label, value }) {
  return (
    <div className="rounded-lg border border-border/70 px-3 py-3">
      <p className="text-xl font-semibold tracking-tight text-foreground">{value}</p>
      <p className="mt-0.5 text-xs leading-4 text-muted-foreground">{label}</p>
    </div>
  );
}

function HistorySources() {
  return (
    <section id="how-it-works" className="scroll-mt-24">
      <div className="max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">How it works</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          Start with the listening history you already have.
        </h2>
        <p className="mt-3 text-base leading-7 text-muted-foreground">
          Add one album, bring in years of listening, or let Albumary keep tracking as you listen.
        </p>
      </div>

      <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {HISTORY_SOURCES.map((source, index) => {
          const Icon = source.icon;
          return (
            <article key={source.title} className="rounded-xl border border-border/80 bg-card p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="size-5" />
                </span>
                <span className="text-xs font-medium text-muted-foreground">0{index + 1}</span>
              </div>
              <h3 className="mt-5 font-semibold tracking-tight text-foreground">{source.title}</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{source.description}</p>
            </article>
          );
        })}
      </div>

      <p className="mt-4 flex items-start gap-2 text-sm leading-6 text-muted-foreground">
        <Disc3 className="mt-1 size-4 shrink-0 text-primary" />
        Albumary is organized around completed album listens—not every individual song play.
      </p>
    </section>
  );
}
