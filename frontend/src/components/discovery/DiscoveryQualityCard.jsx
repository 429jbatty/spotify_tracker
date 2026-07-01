import { useMemo } from "react";
import { buildDiscoveryQuality } from "@/components/utils/discoveryQuality";

const BUCKET_STYLES = {
  1: "bg-chart-1",
  2: "bg-chart-1",
  3: "bg-chart-1",
  4: "bg-chart-1",
  5: "bg-chart-2",
  6: "bg-chart-2",
  7: "bg-chart-2",
  8: "bg-chart-3",
  9: "bg-chart-3",
  10: "bg-chart-3",
};

function formatPercent(value) {
  return `${Math.round(value)}%`;
}

function BucketLegend({ bucket, total }) {
  const percentage = total === 0 ? 0 : (bucket.count / total) * 100;

  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="flex min-w-0 items-center gap-2 text-muted-foreground">
        <span className={`size-3 rounded-sm ${BUCKET_STYLES[bucket.score]}`} />
        <span className="truncate">{bucket.label}</span>
      </span>
      <span className="shrink-0 font-medium text-foreground">
        {bucket.count} · {formatPercent(percentage)}
      </span>
    </div>
  );
}

export default function DiscoveryQualityCard({ listens, selectedRange }) {
  const quality = useMemo(
    () => buildDiscoveryQuality(listens, selectedRange),
    [listens, selectedRange]
  );
  const visibleBuckets = quality.buckets.filter((bucket) => bucket.count > 0);

  return (
    <section className="rounded-lg border border-border/80 bg-background p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-foreground">
            Discovery quality
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            How your new finds scored.
          </p>
        </div>

        {quality.ratedDiscoveries > 0 ? (
          <div className="text-left sm:text-right">
            <p className="text-2xl font-semibold tracking-tight text-foreground">
              Avg score: {quality.averageScore.toFixed(1)}
            </p>
            <p className="text-sm text-muted-foreground">
              {formatPercent(quality.percentGreat)} scored 8+
            </p>
          </div>
        ) : null}
      </div>

      {quality.totalDiscoveries === 0 ? (
        <div className="mt-4 rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          No first-time album discoveries in this range.
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          <div
            aria-label="Discovery quality distribution"
            className="flex h-5 overflow-hidden rounded-sm bg-muted"
            role="img"
          >
            {quality.buckets.map((bucket) => {
              const percentage =
                quality.ratedDiscoveries === 0
                  ? 0
                  : (bucket.count / quality.ratedDiscoveries) * 100;
              if (percentage === 0) return null;

              return (
                <div
                  key={bucket.key}
                  className={BUCKET_STYLES[bucket.score]}
                  style={{ width: `${percentage}%` }}
                  title={`${bucket.label}: ${bucket.count}`}
                />
              );
            })}
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            {visibleBuckets.map((bucket) => (
              <BucketLegend
                key={bucket.key}
                bucket={bucket}
                total={quality.ratedDiscoveries}
              />
            ))}
          </div>

          {quality.ratedDiscoveries === 0 ? (
            <p className="text-sm text-muted-foreground">
              {quality.totalDiscoveries} discoveries in range, none scored yet.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              {quality.ratedDiscoveries} of {quality.totalDiscoveries} discoveries scored
              {quality.unratedDiscoveries > 0
                ? `; ${quality.unratedDiscoveries} unrated not shown in chart.`
                : "."}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
