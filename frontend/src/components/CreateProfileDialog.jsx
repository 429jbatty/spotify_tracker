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
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(false);
  const displayNameId = useId();
  const errorId = useId();
  const slug = profileSlugFromName(displayName);

  const reset = () => {
    setDisplayName("");
    setEmail("");
    setPassword("");
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
    if (!email.trim() || !password) {
      setError("Enter an email address and password to protect this profile.");
      return;
    }
    if (password.length < 12) {
      setError("Use a password with at least 12 characters.");
      return;
    }

    setError(null);
    setPending(true);
    try {
      await onCreateProfile({ display_name: trimmedName, slug, email, password });
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
          <div className="space-y-2">
            <label htmlFor="profile-email" className="text-sm font-medium text-foreground">Email</label>
            <Input
              id="profile-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              disabled={pending}
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="profile-password" className="text-sm font-medium text-foreground">Password</label>
            <Input
              id="profile-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              minLength={12}
              disabled={pending}
            />
            <p className="text-sm text-muted-foreground">Use at least 12 characters. This account owns and protects your profile.</p>
          </div>

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
