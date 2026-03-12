import React, { useMemo, useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getNiceStep } from "./utils/chartUtils";

function ReleaseDateChart({
  albums,
  selectedFilter,
  onSelect,
  onReset,
  chartMode, // "decade" | "year"
  onToggle, // new prop to control chart mode externally
  chartWidth = 800,
  chartHeight = 300
}) {
  const margin = { top: 20, right: 20, bottom: 50, left: 50 };
  const innerWidth = chartWidth - margin.left - margin.right;
  const innerHeight = chartHeight - margin.top - margin.bottom;
  const barGap = 2;

  const [hoveredBar, setHoveredBar] = useState(null);

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

  const currentMax = bars.length > 0 ? Math.max(...bars.map((b) => b.count)) : 1;

  const tickCount = 5;
  const step = getNiceStep(currentMax, tickCount);
  const niceMax = Math.ceil(currentMax / step) * step;
  const tickValues = [];
  for (let i = 0; i <= niceMax; i += step) tickValues.push(i);

  const barWidth = bars.length > 0 ? innerWidth / bars.length - barGap : 0;

  /* ============================================================
     Theme Colors
  ============================================================ */
  const fillColor = "#ffc973"; // base bar
  const selectedColor = "#ff6b3c"; // selected
  const hoverColor = "#ff7f50"; // hover
  const axisColor = "#666"; // subtle axis
  const labelColor = "#333";

  return (
    <Card className="bg-gray-50 rounded-xl shadow-md p-4">
      {/* Header + Toggle */}
      <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4">
        <CardTitle className="text-lg font-bold text-foreground">
          Album Releases
        </CardTitle>

        {/* Chart Mode Toggle inside chart */}
        <Tabs
          value={chartMode}
          onValueChange={(value) => onToggle(value)} // call parent to update
          className="w-full sm:w-auto"
        >
          <TabsList className="grid grid-cols-2 rounded-lg bg-gray-100 p-1">
            <TabsTrigger
              value="year"
              className="data-[state=active]:bg-orange-200 data-[state=active]:text-orange-700"
            >
              Year
            </TabsTrigger>
            <TabsTrigger
              value="decade"
              className="data-[state=active]:bg-orange-200 data-[state=active]:text-orange-700"
            >
              Decade
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </CardHeader>

      {/* Chart */}
      <CardContent>
        <svg width={chartWidth} height={chartHeight} onClick={onReset} style={{ cursor: "pointer" }}>
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
            <line x1={0} y1={innerHeight} x2={innerWidth} y2={innerHeight} stroke={axisColor} strokeWidth={1.5} />

            {/* Bars */}
            {bars.map((bar, index) => {
              const barHeight = (bar.count / niceMax) * innerHeight;
              const x = index * (barWidth + barGap);
              const y = innerHeight - barHeight;

              const isSelected =
                chartMode === "decade"
                  ? selectedFilter.decade === bar.label
                  : selectedFilter.year === bar.label;

              return (
                <g key={bar.label} transform={`translate(${x},0)`}>
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
                          ? "drop-shadow(0 2px 6px rgba(255,107,60,0.5))"
                          : "none",
                    }}
                    onMouseEnter={(e) =>
                      setHoveredBar({
                        label: bar.label,
                        count: bar.count,
                        x, // SVG relative
                        y,
                      })
                    }
                    onMouseLeave={() => setHoveredBar(null)}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (chartMode === "decade") {
                        onSelect(bar.label, null);
                      } else {
                        onSelect(Math.floor(bar.label / 10) * 10, bar.label);
                      }
                    }}
                  />

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

            {/* Tooltip inside SVG */}
            {hoveredBar && (
              <g transform={`translate(${hoveredBar.x + barWidth + 8}, ${hoveredBar.y})`} pointerEvents="none">
                <rect x={0} y={-20} width={80} height={32} fill="white" stroke="#ccc" rx={4} ry={4} />
                <text x={40} y={-8} textAnchor="middle" fontSize={10} fill="#333">
                  {chartMode === "decade" ? "Decade" : "Year"}: {hoveredBar.label}
                </text>
                <text x={40} y={6} textAnchor="middle" fontSize={10} fill="#333">
                  Count: {hoveredBar.count}
                </text>
              </g>
            )}
          </g>
        </svg>
      </CardContent>
    </Card>
  );
}

export default ReleaseDateChart;