import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export default function LoginDialog({ open, onOpenChange, onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await onLogin({ email, password });
      onOpenChange(false);
    } catch (requestError) {
      setError(requestError?.message || "Could not sign in.");
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Sign in</DialogTitle>
          <DialogDescription>Sign in to manage your Albumary profile.</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={submit}>
          <Input type="email" placeholder="Email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <Input type="password" placeholder="Password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button className="w-full" disabled={pending}>{pending ? "Signing in..." : "Sign in"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
