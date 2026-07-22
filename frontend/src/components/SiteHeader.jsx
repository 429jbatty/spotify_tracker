import { Library } from "lucide-react";

import { Button } from "@/components/ui/button";

function SiteHeader({
  context,
  onBrowseProfiles,
  onAbout,
  onLogin,
  primaryAction,
  authenticatedAccount,
  children,
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-border/70 bg-background/95 text-foreground backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onBrowseProfiles}
          className="flex min-w-0 items-center gap-3 text-left"
          aria-label="Browse Albumary profiles"
        >
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
            <Library className="size-5" />
          </span>
          <span className="min-w-0">
            <span className="block text-lg font-semibold tracking-tight">Albumary</span>
            {context && <span className="block truncate text-xs text-muted-foreground">{context}</span>}
          </span>
        </button>

        <nav className="flex items-center gap-2 text-sm font-medium text-muted-foreground sm:gap-4">
          <Button type="button" variant="ghost" size="sm" onClick={onBrowseProfiles}>Browse profiles</Button>
          {onAbout && <button type="button" onClick={onAbout} className="hidden transition-colors hover:text-foreground sm:block">About</button>}
          {authenticatedAccount ? (
            <span className="max-w-44 truncate rounded-full border border-primary/20 bg-primary/5 px-2.5 py-1.5 text-xs text-foreground" title={`Signed in as ${authenticatedAccount.email}`}>
              <span className="hidden sm:inline">Signed in as {authenticatedAccount.email}</span>
              <span className="sm:hidden">Signed in</span>
            </span>
          ) : onLogin ? <button type="button" onClick={onLogin} className="transition-colors hover:text-foreground">Sign in</button> : null}
          {primaryAction && <Button type="button" size="sm" onClick={primaryAction.onClick}>{primaryAction.label}</Button>}
        </nav>
      </div>
      {children && <div className="border-t border-border/60 bg-muted/30">{children}</div>}
    </header>
  );
}

export default SiteHeader;
