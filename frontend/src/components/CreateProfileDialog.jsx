import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { profileSlugFromName } from "@/components/utils/profileSlug";

function CreateProfileDialog({ open, onOpenChange, onCreateProfile }) {
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(false);
  const displayNameId = useId();
  const errorId = useId();
  const slug = profileSlugFromName(displayName);

  const reset = () => {
    setDisplayName("");
    setError(null);
    setPending(false);
  };

  const handleOpenChange = (nextOpen) => {
    if (pending) return;
    if (!nextOpen) reset();
    onOpenChange(nextOpen);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const trimmedName = displayName.trim();

    if (!trimmedName) {
      setError("Enter a profile name to continue.");
      return;
    }
    if (!slug) {
      setError("Use a profile name with at least one letter or number.");
      return;
    }
    setError(null);
    setPending(true);
    try {
      await onCreateProfile({ display_name: trimmedName, slug });
      reset();
      onOpenChange(false);
    } catch (requestError) {
      setError(requestError?.message || "Could not create the profile. Please try again.");
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create your profile</DialogTitle>
          <DialogDescription>
            Start an album listening history. Your profile URL will be created from your name.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label htmlFor={displayNameId} className="text-sm font-medium text-foreground">
              Profile name
            </label>
            <Input
              id={displayNameId}
              value={displayName}
              onChange={(event) => {
                setDisplayName(event.target.value);
                if (error) setError(null);
              }}
              placeholder="Your name"
              autoComplete="name"
              autoFocus
              aria-describedby={error ? errorId : undefined}
              aria-invalid={Boolean(error)}
              disabled={pending}
            />
            {slug && (
              <p className="text-sm text-muted-foreground">Your profile URL: /{slug}</p>
            )}
          </div>
          <p className="text-sm text-muted-foreground">Your signed-in Google account will own this profile.</p>

          {error && (
            <p id={errorId} role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={pending}>
            {pending ? "Creating profile..." : "Create profile"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default CreateProfileDialog;
