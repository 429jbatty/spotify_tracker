import { IMPORT_GUIDES } from "./importDialogConfig";

export function SummaryStat({ label, value }) {
  return (
    <div className="rounded-xl border border-border/70 bg-background/70 p-3">
      <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
    </div>
  );
}

export function SourceGuide({ source }) {
  const guide = IMPORT_GUIDES[source];
  if (!guide) return null;

  return (
    <section className="rounded-xl border border-border/70 bg-muted/20 p-4">
      <p className="text-sm font-semibold text-foreground">{guide.title}</p>
      <p className="mt-2 text-sm text-muted-foreground">{guide.intro}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {guide.points.map((point) => (
          <p
            key={point}
            className="rounded-md border border-border/70 bg-background/70 px-2.5 py-1 text-xs text-foreground"
          >
            {point}
          </p>
        ))}
      </div>
      <div className="mt-3 rounded-lg border border-border/70 bg-background/80 p-3">
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
          {guide.exampleLabel}
        </p>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs text-foreground">
          {guide.example}
        </pre>
      </div>
    </section>
  );
}
