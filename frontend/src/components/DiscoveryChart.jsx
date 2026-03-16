import React, { useMemo, useState, useEffect } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

const TIME_RANGES = {
  "7d": 7,
  "30d": 30,
  "1y": 365,
  all: Infinity,
};

function formatDate(dateStr, timeRange) {
  const d = new Date(dateStr);

  if (timeRange === "7d" || timeRange === "30d") {
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

function getSeparatedY(valA, valB, scaleY) {
  const baseA = scaleY(valA);
  const baseB = scaleY(valB);

  const GAP = 3;

  if (Math.abs(baseA - baseB) < GAP * 2) {
    return [baseA - GAP, baseB + GAP];
  }

  return [baseA, baseB];
}

export default function DiscoveryLineChart({
  albums,
  timeRange,
  chartHeight = 260,
}) {
  const [chartWidth, setChartWidth] = useState(800);
  const [hoveredPoint, setHoveredPoint] = useState(null);

  useEffect(() => {
    const handleResize = () => setChartWidth(window.innerWidth - 80);
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const margin = { top: 30, right: 30, bottom: 55, left: 50 };

  const innerWidth = chartWidth - margin.left - margin.right;
  const innerHeight = chartHeight - margin.top - margin.bottom;

  const chartData = useMemo(() => {
    const albumsArray = Object.values(albums);

    const now = new Date();
    let cutoff = new Date(0);

    if (timeRange !== "all") {
      cutoff = new Date(
        now.getTime() - TIME_RANGES[timeRange] * 24 * 60 * 60 * 1000
      );
    }

    const entries = [];
    const seenArtists = new Set();

    albumsArray.forEach((album) => {
      album.listen_history?.forEach((dateStr) => {
        const date = new Date(dateStr);

        if (date >= cutoff) {
          const isNewArtist = !seenArtists.has(album.artist);

          entries.push({
            date,
            isNewArtist,
          });

          if (isNewArtist) seenArtists.add(album.artist);
        }
      });
    });

    const dayMap = {};

    entries.forEach(({ date, isNewArtist }) => {
      const key = date.toISOString().split("T")[0];

      if (!dayMap[key]) {
        dayMap[key] = {
          date: key,
          newAlbums: 0,
          newArtists: 0,
        };
      }

      dayMap[key].newAlbums += 1;

      if (isNewArtist) {
        dayMap[key].newArtists += 1;
      }
    });

    return Object.values(dayMap).sort(
      (a, b) => new Date(a.date) - new Date(b.date)
    );
  }, [albums, timeRange]);

  const maxY = Math.max(
    1,
    ...chartData.flatMap((d) => [d.newAlbums, d.newArtists])
  );

  const scaleX = (i) =>
    (i / Math.max(chartData.length - 1, 1)) * innerWidth;

  const scaleY = (v) =>
    innerHeight - (v / maxY) * innerHeight;

  const albumPoints = [];
  const artistPoints = [];

  chartData.forEach((d, i) => {
    const x = scaleX(i);

    const [albumY, artistY] = getSeparatedY(
      d.newAlbums,
      d.newArtists,
      scaleY
    );

    albumPoints.push({ x, y: albumY, value: d.newAlbums, date: d.date });
    artistPoints.push({ x, y: artistY, value: d.newArtists, date: d.date });
  });

  const tickEvery = Math.max(1, Math.floor(chartData.length / 10));
  const xTicks = chartData.filter((_, i) => i % tickEvery === 0);

  return (
    <Card className="w-full">
      <CardHeader className="flex justify-between items-center">
        <CardTitle>New Discoveries Over Time</CardTitle>

        <div className="flex gap-4 text-sm">
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 bg-chart-1 rounded-sm" />
            New Albums
          </div>

          <div className="flex items-center gap-1">
            <div className="w-3 h-3 bg-primary rounded-sm" />
            New Artists
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <svg width={chartWidth} height={chartHeight}>
          <g transform={`translate(${margin.left},${margin.top})`}>

            {/* Y grid lines */}
            {[0, maxY / 2, maxY].map((tick, i) => {
              const y = scaleY(tick);

              return (
                <g key={i}>
                  <line
                    x1={0}
                    x2={innerWidth}
                    y1={y}
                    y2={y}
                    stroke="var(--muted-foreground)"
                  />

                  <text
                    x={-8}
                    y={y + 4}
                    fontSize={10}
                    textAnchor="end"
                    fill="var(--foreground)"
                  >
                    {Math.round(tick)}
                  </text>
                </g>
              );
            })}

            {/* Y label */}
            <text
              transform={`translate(-38,${innerHeight / 2}) rotate(-90)`}
              textAnchor="middle"
              fontSize={12}
              fill="var(--foreground)"
            >
              Count
            </text>

            {/* X axis */}
            <line
              x1={0}
              y1={innerHeight}
              x2={innerWidth}
              y2={innerHeight}
              stroke="var(--muted-foreground)"
            />

            {xTicks.map((d, i) => {
              const idx = chartData.indexOf(d);
              const x = scaleX(idx);

              return (
                <text
                  key={i}
                  x={x}
                  y={innerHeight + 18}
                  textAnchor="middle"
                  fontSize={10}
                  fill="var(--foreground)"
                >
                  {formatDate(d.date, timeRange)}
                </text>
              );
            })}

            {/* X label */}
            <text
              x={innerWidth / 2}
              y={innerHeight + 40}
              textAnchor="middle"
              fontSize={12}
              fill="var(--foreground)"
            >
              Date
            </text>

            {/* Album line */}
            <polyline
              fill="none"
              stroke="var(--chart-1)"
              strokeWidth={2}
              points={albumPoints.map(p => `${p.x},${p.y}`).join(" ")}
            />

            {/* Artist line */}
            <polyline
              fill="none"
              stroke="var(--primary)"
              strokeWidth={2}
              points={artistPoints.map(p => `${p.x},${p.y}`).join(" ")}
            />

            {/* Album points */}
            {albumPoints.map((p, i) => (
              <circle
                key={`album-${i}`}
                cx={p.x}
                cy={p.y}
                r={4}
                fill="var(--chart-1)"
                onMouseEnter={() =>
                  setHoveredPoint({
                    label: "New Albums",
                    ...p,
                  })
                }
                onMouseLeave={() => setHoveredPoint(null)}
              />
            ))}

            {/* Artist points */}
            {artistPoints.map((p, i) => (
              <circle
                key={`artist-${i}`}
                cx={p.x}
                cy={p.y}
                r={4}
                fill="var(--primary)"
                onMouseEnter={() =>
                  setHoveredPoint({
                    label: "New Artists",
                    ...p,
                  })
                }
                onMouseLeave={() => setHoveredPoint(null)}
              />
            ))}

            {/* Tooltip */}
            {hoveredPoint && (
              <g
                transform={`translate(${hoveredPoint.x + 10},${hoveredPoint.y - 32})`}
                pointerEvents="none"
              >
                <rect
                  width="130"
                  height="40"
                  rx="4"
                  fill="var(--muted)"
                />

                <text
                  x="6"
                  y="14"
                  fontSize="10"
                  fill="var(--foreground)"
                >
                  {hoveredPoint.label}: {hoveredPoint.value}
                </text>

                <text
                  x="6"
                  y="28"
                  fontSize="10"
                  fill="var(--foreground)"
                >
                  {formatDate(hoveredPoint.date, timeRange)}
                </text>
              </g>
            )}

          </g>
        </svg>
      </CardContent>
    </Card>
  );
}