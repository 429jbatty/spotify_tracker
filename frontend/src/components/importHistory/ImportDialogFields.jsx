import { IMPORT_GUIDES } from "./importDialogConfig";

export function SummaryStat({ label, value }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background p-3">
      <p className="text-xs font-medium text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold text-foreground">
        {Number(value || 0).toLocaleString()}
      </p>
    </div>
  );
}

export function SourceGuide({ source }) {
  const guide = IMPORT_GUIDES[source];
  if (!guide) return null;

  return (
    <section>
      <p className="text-sm font-semibold text-foreground">{guide.title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{guide.intro}</p>
    </section>
  );
}
