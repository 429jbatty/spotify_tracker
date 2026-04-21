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
      <div className="mx-auto flex max-w-3xl flex-col gap-8">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold">Albumary</h1>
          <p className="text-sm text-muted-foreground">
            Choose a listener to open their album history.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {users.map((user) => (
            <button
              key={user.slug}
              type="button"
              onClick={() => onSelectUser(user)}
              className="rounded-md border border-border bg-card px-4 py-4 text-left hover:bg-muted"
            >
              <span className="block text-base font-medium">
                {user.display_name}
              </span>
            </button>
          ))}
        </div>

        <form
          onSubmit={handleCreate}
          className="flex flex-col gap-3 border-t border-border pt-6 sm:flex-row"
        >
          <Input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            placeholder="Add a listener"
          />
          <Button type="submit">Create</Button>
        </form>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    </main>
  );
}

export default UserHome;
