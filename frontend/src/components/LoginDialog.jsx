import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export default function LoginDialog({ open, onOpenChange, onLogin }) {
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(false);
  const signIn = async () => {
    setPending(true);
    setError(null);
    try {
      await onLogin();
    } catch (requestError) {
      setPending(false);
      setError(requestError?.message || "Could not start Google sign-in.");
    }
  };
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>Sign in</DialogTitle><DialogDescription>Sign in with Google to manage your Albumary profile.</DialogDescription></DialogHeader>{error && <p className="text-sm text-destructive">{error}</p>}<Button className="w-full" disabled={pending} onClick={signIn}>{pending ? "Opening Google..." : "Continue with Google"}</Button></DialogContent></Dialog>;
}
