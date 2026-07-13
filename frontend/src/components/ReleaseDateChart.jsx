import React, { useMemo, useRef, useState } from "react";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getNiceStep } from "./utils/chartUtils";
import { useElementSize } from "@/hooks/useElementSize";

function ReleaseDateChart({
  albums,
  selectedFilter,
  onSelect,
  onReset,
  chartMode, // "decade" | "year"
  onToggle,
  chartHeight = 300,
}) {
  const chartRef = useRef(null);
  const { width: containerWidth } = useElementSize(chartRef);
  const margin = { top: 16, right: 24, bottom: 56, left: 52 };
  const barGap = 4;
  const [hoveredBar, setHoveredBar] = useState(null);
  const [focusedBar, setFocusedBar] = useState(null);

  // -----------------------
  // Compute bars
  // -----------------------
  const albumsPerDecade = useMemo(() => {
    const decadeMap = {};
    Object.values(albums).forEach((album) => {
      if (!album.release_date) return;
      const year = parseInt(album.release_date.slice(0, 4));
      const decade = Math.floor(year / 10) * 10;
      if (!decadeMap[decade]) decadeMap[decade] = { decade, count: 0, years: {} };
      decadeMap[decade].count += 1;
      decadeMap[decade].years[year] = (decadeMap[decade].years[year] || 0) + 1;
    });
    return Object.values(decadeMap).sort((a, b) => a.decade - b.decade);
  }, [albums]);

  const allYears = useMemo(() => {
    const yearMap = {};
    albumsPerDecade.forEach((decade) => {
      Object.entries(decade.years).forEach(([year, count]) => {
        yearMap[year] = count;
      });
    });
    return Object.entries(yearMap)
      .map(([year, count]) => ({ year: parseInt(year), count }))
      .sort((a, b) => a.year - b.year);
  }, [albumsPerDecade]);

  const bars =
    chartMode === "decade"
      ? albumsPerDecade.map((d) => ({ label: d.decade, count: d.count }))
      : allYears.map((y) => ({ label: y.year, count: y.count }));

  const minimumBarPitch = 48;
  const minChartWidth = margin.left + margin.right + bars.length * minimumBarPitch;
  const chartWidth = Math.max(containerWidth || 1, minChartWidth);
  const chartScrolls = chartWidth > (containerWidth || chartWidth);
  const innerWidth = Math.max(1, chartWidth - margin.left - margin.right);
  const innerHeight = chartHeight - margin.top - margin.bottom;
  const currentMax = bars.length > 0 ? Math.max(...bars.map((b) => b.count)) : 1;
  const tickCount = 5;
  const step = getNiceStep(currentMax, tickCount);
  const niceMax = Math.ceil(currentMax / step) * step;
  const tickValues = [];
  for (let i = 0; i <= niceMax; i += step) tickValues.push(i);

  const barWidth = bars.length > 0 ? innerWidth / bars.length - barGap : 0;

  // -----------------------
  // Theme colors
  // -----------------------
  const fillColor = "var(--chart-1)";
  const selectedColor = "var(--primary)";
  const hoverColor = "var(--primary)";
  const axisColor = "var(--muted-foreground)";
  const labelColor = "var(--foreground)";

  const selectBar = (bar) => {
    const isAlreadySelected =
      chartMode === "decade"
        ? selectedFilter.decade === bar.label
        : selectedFilter.year === bar.label;

    if (isAlreadySelected) {
      onSelect(null, null);
    } else if (chartMode === "decade") {
      onSelect(bar.label, null);
    } else {
      onSelect(Math.floor(bar.label / 10) * 10, bar.label);
    }
  };

  const handleBarKeyDown = (event, bar) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    selectBar(bar);
  };

  return (
    <Card className="w-full rounded-lg bg-background/85 ring-foreground/5">
      <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <CardTitle>Albums by release date</CardTitle>
          <CardDescription>
            Browse the library by original release year or decade.
          </CardDescription>
        </div>

        <div className="flex shrink-0">
          <Tabs value={chartMode} onValueChange={onToggle}>
            <TabsList className="grid grid-cols-2 rounded-md bg-muted p-1">
              <TabsTrigger
                value="year"
                className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                Year
              </TabsTrigger>
              <TabsTrigger
                value="decade"
                className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                Decade
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </CardHeader>

      <CardContent
        ref={chartRef}
        className="w-full overflow-x-auto pb-4"
        aria-label={
          chartScrolls
            ? `Release dates by ${chartMode}. Scroll horizontally to reach every ${chartMode === "year" ? "year" : "decade"}.`
            : "Release dates by decade."
        }
      >
        {chartScrolls && (
          <p className="mb-3 text-xs text-muted-foreground">
            Scroll horizontally to browse every {chartMode === "year" ? "year" : "decade"}. Select a bar to filter the library.
          </p>
        )}
        <svg
          width={chartWidth}
          height={chartHeight}
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          onClick={onReset}
          style={{ cursor: "pointer" }}
        >
          <g transform={`translate(${margin.left}, ${margin.top})`}>
            {/* Y-Axis */}
            <g>
              {tickValues.map((value, index) => {
                const y = innerHeight - (value / niceMax) * innerHeight;
                return (
                  <g key={index} transform={`translate(0, ${y})`}>
                    <line x1={0} x2={-5} y1={0} y2={0} stroke={axisColor} />
                    <text x={-10} y={4} textAnchor="end" fontSize={10} fill={labelColor}>
                      {value}
                    </text>
                  </g>
                );
              })}
              <line x1={0} y1={0} x2={0} y2={innerHeight} stroke={axisColor} />
            </g>

            {/* X-Axis */}
            <line
              x1={0}
              y1={innerHeight}
              x2={innerWidth}
              y2={innerHeight}
              stroke={axisColor}
              strokeWidth={1.5}
            />

            {/* Bars */}
            {bars.length === 0 && (
              <text
                x={innerWidth / 2}
                y={innerHeight / 2}
                textAnchor="middle"
                fontSize={13}
                fill="var(--muted-foreground)"
              >
                No release dates available.
              </text>
            )}

            {bars.map((bar, index) => {
              const barHeight = (bar.count / niceMax) * innerHeight;
              const x = index * (barWidth + barGap);
              const y = innerHeight - barHeight;

              const isSelected =
                chartMode === "decade"
                  ? selectedFilter.decade === bar.label
                  : selectedFilter.year === bar.label;

              return (
                <g
                  key={bar.label}
                  transform={`translate(${x},0)`}
                  role="button"
                  tabIndex={0}
                  aria-label={`${chartMode === "decade" ? "Decade" : "Year"} ${bar.label}: ${bar.count} album${bar.count === 1 ? "" : "s"}`}
                  aria-pressed={isSelected}
                  onKeyDown={(event) => handleBarKeyDown(event, bar)}
                  onFocus={() => {
                    setFocusedBar(bar.label);
                    setHoveredBar({ label: bar.label, count: bar.count, x, y });
                  }}
                  onBlur={() => {
                    setFocusedBar(null);
                    setHoveredBar(null);
                  }}
                >
                  <rect
                    x={0}
                    y={0}
                    width={barWidth + barGap}
                    height={innerHeight}
                    fill="transparent"
                    onMouseEnter={() =>
                      setHoveredBar({ label: bar.label, count: bar.count, x, y })
                    }
                    onMouseLeave={() => setHoveredBar(null)}
                    onClick={(event) => {
                      event.stopPropagation();
                      selectBar(bar);
                    }}
                  />
                  <rect
                    x={0}
                    y={y}
                    width={barWidth}
                    height={barHeight}
                    rx={2}
                    ry={2}
                    fill={isSelected ? selectedColor : fillColor}
                    style={{
                      cursor: "pointer",
                      transition: "fill 0.2s, transform 0.2s, filter 0.2s",
                      transformOrigin: "bottom",
                      transform: hoveredBar?.label === bar.label ? "scaleY(1.05)" : "scaleY(1)",
                      filter:
                        hoveredBar?.label === bar.label
                          ? `drop-shadow(0 2px 6px ${hoverColor}80)`
                          : "none",
                    }}
                    pointerEvents="none"
                  />
                  {focusedBar === bar.label && (
                    <rect
                      x={-1}
                      y={-1}
                      width={barWidth + 2}
                      height={innerHeight + 2}
                      fill="none"
                      stroke="var(--ring)"
                      strokeWidth={2}
                      pointerEvents="none"
                    />
                  )}

                  {(chartMode === "decade" || index % 2 === 0) && (
                    <text
                      x={barWidth / 2}
                      y={innerHeight + 12}
                      textAnchor="end"
                      fontSize={10}
                      transform={`rotate(-45, ${barWidth / 2}, ${innerHeight + 12})`}
                      fill={labelColor}
                    >
                      {bar.label}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Tooltip */}
            {hoveredBar && (() => {
              const tooltipWidth = 80;
              const tooltipHeight = 32;
              const margin = 8;
              let tooltipX = hoveredBar.x + barWidth + margin;
              let tooltipAnchor = "middle";

              // If tooltip would overflow right edge, position to the left
              if (tooltipX + tooltipWidth > .85 * innerWidth) {
                tooltipX = hoveredBar.x - tooltipWidth - margin;
                tooltipAnchor = "middle"; // text still centered in rect
              }

              return (
                <g transform={`translate(${tooltipX}, ${hoveredBar.y})`} pointerEvents="none">
                  <rect
                    x={0}
                    y={-tooltipHeight / 2}
                    width={tooltipWidth}
                    height={tooltipHeight}
                    fill="var(--muted)"
                    stroke="var(--border)"
                    rx={4}
                    ry={4}
                  />
                  <text
                    x={tooltipWidth / 2}
                    y={-4}
                    textAnchor={tooltipAnchor}
                    fontSize={10}
                    fill="var(--foreground)"
                  >
                    {chartMode === "decade" ? "Decade" : "Year"}: {hoveredBar.label}
                  </text>
                  <text
                    x={tooltipWidth / 2}
                    y={8}
                    textAnchor={tooltipAnchor}
                    fontSize={10}
                    fill="var(--foreground)"
                  >
                    Count: {hoveredBar.count}
                  </text>
                </g>
              );
            })()}
          </g>
        </svg>
      </CardContent>
    </Card>
  );
}

export default ReleaseDateChart;
