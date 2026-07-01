import { useMemo } from "react";
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  LinearScale,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";
import { getChartColor } from "./chartTheme";

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip);

function LegendItem({ color, label }) {
  return (
    <span className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="size-3 rounded-sm" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

export default function NewVsReplayTrend({ series }) {
  const hasActivity = series.some((point) => point.total > 0);
  const data = useMemo(
    () => ({
      labels: series.map((point) => point.label),
      datasets: [
        {
          backgroundColor: getChartColor("--chart-3"),
          borderSkipped: false,
          data: series.map((point) => point.discoveries),
          label: "New discoveries",
        },
        {
          backgroundColor: getChartColor("--chart-1"),
          borderSkipped: false,
          data: series.map((point) => point.replays),
          label: "Replays",
        },
      ],
    }),
    [series]
  );

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            footer: (items) => {
              const point = series[items[0]?.dataIndex];
              return point ? point.rangeLabel : "";
            },
            label: (context) =>
              `${context.dataset.label}: ${context.parsed.y.toLocaleString()}`,
          },
        },
      },
      scales: {
        x: {
          stacked: true,
          border: { display: false },
          grid: { display: false },
          ticks: {
            autoSkip: true,
            color: getChartColor("--muted-foreground"),
            font: { size: 10 },
            maxRotation: 0,
            maxTicksLimit: 8,
          },
        },
        y: {
          beginAtZero: true,
          stacked: true,
          border: { display: false },
          grid: { color: "rgba(115, 115, 115, 0.14)" },
          ticks: {
            color: getChartColor("--muted-foreground"),
            precision: 0,
          },
        },
      },
    }),
    [series]
  );

  return (
    <section className="rounded-lg border border-border/80 bg-background p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-foreground">
            New vs replay trend
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            How much of each period came from exploration versus revisiting.
          </p>
        </div>
        <div className="flex flex-wrap gap-4">
          <LegendItem color={getChartColor("--chart-3")} label="New discoveries" />
          <LegendItem color={getChartColor("--chart-1")} label="Replays" />
        </div>
      </div>

      {hasActivity ? (
        <div className="mt-4 h-60">
          <Bar
            aria-label="New discoveries compared with replay listens over time"
            data={data}
            options={options}
            role="img"
          />
        </div>
      ) : (
        <div className="mt-4 flex h-60 items-center justify-center text-sm text-muted-foreground">
          Discovery and replay trends will appear after dated listens are available.
        </div>
      )}
    </section>
  );
}
