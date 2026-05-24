import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function slugFromName(value) {
  return value.trim().toLowerCase().replace(/\s+/g, "-");
}

function UserHome({ users, onSelectUser, onCreateUser }) {
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState(null);

  const handleCreate = async (event) => {
    event.preventDefault();
    const trimmedName = displayName.trim();
    if (!trimmedName) return;

    try {
      setError(null);
      const user = await onCreateUser({
        display_name: trimmedName,
        slug: slugFromName(trimmedName),
      });
      setDisplayName("");
      onSelectUser(user);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <main className="min-h-screen bg-background px-6 py-10 text-foreground">
      <div className="mx-auto flex max-w-6xl flex-col gap-10 lg:grid lg:grid-cols-[1.1fr_0.9fr] lg:items-start">
        <section className="relative overflow-hidden rounded-3xl border border-border/70 bg-[linear-gradient(135deg,rgba(236,201,75,0.16),rgba(255,255,255,0.02)_42%,rgba(114,160,193,0.14))] p-8 shadow-sm lg:min-h-[32rem]">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.18),transparent_35%),radial-gradient(circle_at_bottom_right,rgba(255,255,255,0.08),transparent_30%)]" />
          <div className="relative flex h-full flex-col justify-between gap-10">
            <div className="space-y-5">
              <div className="inline-flex items-center rounded-full border border-border/70 bg-background/70 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur">
                Personal album listening history
              </div>
              <div className="space-y-3">
                <h1 className="max-w-xl text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
                  Albumary
                </h1>
                <p className="max-w-xl text-base leading-7 text-muted-foreground sm:text-lg">
                  Track complete album listens over time, attach personal notes and
                  ratings, and build a library that feels closer to a listening
                  journal than a spreadsheet.
                </p>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="rounded-2xl border border-border/70 bg-background/75 p-4 backdrop-blur">
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                  Multi-user
                </p>
                <p className="mt-2 text-sm text-foreground">
                  Separate listening history and Spotify sync for each listener.
                </p>
              </div>
              <div className="rounded-2xl border border-border/70 bg-background/75 p-4 backdrop-blur">
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                  Metadata-rich
                </p>
                <p className="mt-2 text-sm text-foreground">
                  MusicBrainz artwork, credits, release data, and cleanup tools.
                </p>
              </div>
              <div className="rounded-2xl border border-border/70 bg-background/75 p-4 backdrop-blur">
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                  Personal taste
                </p>
                <p className="mt-2 text-sm text-foreground">
                  Ratings, notes, and curated tags for how albums actually land.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-6">
          <div className="rounded-3xl border border-border/70 bg-card p-6 shadow-sm">
            <div className="space-y-2">
              <p className="text-sm font-medium text-muted-foreground">
                Create a listener
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground">
                Start a fresh profile
              </h2>
              <p className="text-sm text-muted-foreground">
                Add a listener profile for someone new, then jump straight into the
                library.
              </p>
            </div>

            <form onSubmit={handleCreate} className="mt-6 space-y-4">
              <Input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Listener name"
              />
              <Button type="submit" className="w-full">
                Create listener
              </Button>
              {error && <p className="text-sm text-destructive">{error}</p>}
            </form>
          </div>

          <div className="rounded-3xl border border-border/70 bg-card p-6 shadow-sm">
            <div className="space-y-2">
              <p className="text-sm font-medium text-muted-foreground">
                Continue as
              </p>
              <h2 className="text-xl font-semibold tracking-tight text-foreground">
                Existing listener
              </h2>
              <p className="text-sm text-muted-foreground">
                Pick an existing profile to open its listening history.
              </p>
            </div>

            {users.length > 0 ? (
              <div className="mt-5 grid gap-3">
                {users.map((user) => (
                  <button
                    key={user.slug}
                    type="button"
                    onClick={() => onSelectUser(user)}
                    className="rounded-2xl border border-border/70 bg-background px-4 py-4 text-left transition-colors hover:bg-muted/40"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <span className="block text-base font-medium text-foreground">
                          {user.display_name}
                        </span>
                        <span className="mt-1 block text-sm text-muted-foreground">
                          Open listener profile
                        </span>
                      </div>
                      <span className="text-xs font-medium text-muted-foreground">
                        Open
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="mt-5 rounded-2xl border border-dashed border-border/70 bg-background/60 p-5 text-sm text-muted-foreground">
                No listener profiles yet. Create the first one above to get started.
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

export default UserHome;
