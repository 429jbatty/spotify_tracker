import { Info } from "lucide-react";

function formatDelta(delta, comparisonLabel) {
  if (!delta || delta.value == null) return `No ${comparisonLabel}`;
  if (delta.value === 0) return `No change vs ${comparisonLabel}`;

  const sign = delta.value > 0 ? "+" : "";
  const value =
    delta.kind === "count"
      ? Math.round(delta.value).toLocaleString()
      : `${delta.value.toFixed(0)} pts`;

  return `${sign}${value} vs ${comparisonLabel}`;
}

function MetricInfo({ label, tooltip }) {
  if (!tooltip) return null;

  return (
    <span className="group/metric-info relative inline-flex">
      <button
        aria-label={`About ${label}`}
        className="rounded-full p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        type="button"
      >
        <Info className="size-3.5" />
      </button>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-64 -translate-x-1/2 rounded-lg bg-popover p-3 text-left text-xs leading-relaxed text-popover-foreground opacity-0 shadow-md ring-1 ring-foreground/10 transition-opacity group-hover/metric-info:opacity-100 group-focus-within/metric-info:opacity-100">
        {tooltip}
      </span>
    </span>
  );
}

function MetricLabel({ label, tooltip }) {
  return (
    <div className="mt-1 flex items-center justify-center gap-1 text-xs text-muted-foreground sm:text-sm">
      <span>{label}</span>
      <MetricInfo label={label} tooltip={tooltip} />
    </div>
  );
}

function DiscoveryMixBar({ newToYouListeningShare, catalogListeningShare }) {
  return (
    <div className="mx-auto mt-3 flex h-2 max-w-44 overflow-hidden rounded-full bg-chart-1/60">
      <div
        className="h-full bg-chart-3"
        style={{ width: `${Math.max(0, Math.min(100, newToYouListeningShare))}%` }}
      />
      <div
        className="h-full bg-chart-1"
        style={{ width: `${Math.max(0, Math.min(100, catalogListeningShare))}%` }}
      />
    </div>
  );
}

function Metric({
  comparisonLabel,
  delta,
  newToYouListeningShare,
  label,
  catalogListeningShare,
  tooltip,
  type,
  value,
}) {
  const deltaText = formatDelta(delta, comparisonLabel);
  const deltaTone =
    delta?.value == null || delta.value === 0
      ? "text-muted-foreground"
      : delta.value > 0
        ? "text-chart-4"
        : "text-muted-foreground";

  return (
    <div className="min-w-0 px-4 py-4 text-center sm:px-6">
      <p className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
        {value}
      </p>
      {type === "mix" ? (
        <>
          <p className="mt-1 text-sm font-medium text-muted-foreground">
            {catalogListeningShare.toFixed(0)}% catalog
          </p>
          <DiscoveryMixBar
            newToYouListeningShare={newToYouListeningShare}
            catalogListeningShare={catalogListeningShare}
          />
        </>
      ) : null}
      <MetricLabel label={label} tooltip={tooltip} />
      <p className={`mt-1 text-xs font-medium ${deltaTone}`}>{deltaText}</p>
    </div>
  );
}

export default function DiscoveryMetricRail({ metrics }) {
  return (
    <section className="grid grid-cols-1 divide-y divide-border/70 border-y border-border/70 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
      {metrics.map((metric) => (
        <Metric key={metric.label} {...metric} />
      ))}
    </section>
  );
}
