import { IMPORT_GUIDES } from "./importDialogConfig";
import { ExternalLink } from "lucide-react";

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
    <section className="rounded-lg border border-border/70 bg-muted/20 p-4">
      <p className="text-sm font-semibold text-foreground">{guide.title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{guide.intro}</p>
      <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm text-muted-foreground">
        {guide.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      {guide.link ? (
        <a
          className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline"
          href={guide.link.href}
          target="_blank"
          rel="noreferrer"
        >
          {guide.link.label}
          <ExternalLink className="size-3.5" aria-hidden="true" />
        </a>
      ) : null}
      {guide.note ? <p className="mt-3 text-xs text-muted-foreground">{guide.note}</p> : null}
    </section>
  );
}
