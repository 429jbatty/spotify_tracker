import React, { useMemo, useState } from "react";
import { getNiceStep } from "./utils/chartUtils";

function ReleaseDateChart({
  albums,
  selectedFilter,
  onSelect,
  onReset,
  chartMode, // "decade" | "year"
  chartWidth = 800,
  chartHeight = 300
}) {
  /* ============================================================
     Layout Configuration
  ============================================================ */

  const margin = { top: 20, right: 20, bottom: 50, left: 50 };

  const innerWidth = chartWidth - margin.left - margin.right;
  const innerHeight = chartHeight - margin.top - margin.bottom;

  const barGap = 2;

  /* ============================================================
     Hover State (tooltip)
  ============================================================ */

  const [hoveredBar, setHoveredBar] = useState(null);

  /* ============================================================
     Data Aggregation
     - albumsPerDecade → decade totals + year breakdown
     - allYears → flattened list of every year
  ============================================================ */

  const albumsPerDecade = useMemo(() => {
    const decadeMap = {};

    Object.values(albums).forEach((album) => {
      if (!album.release_date) return;

      const year = parseInt(album.release_date.slice(0, 4));
      const decade = Math.floor(year / 10) * 10;

      if (!decadeMap[decade]) {
        decadeMap[decade] = {
          decade,
          count: 0,
          years: {}
        };
      }

      decadeMap[decade].count += 1;
      decadeMap[decade].years[year] =
        (decadeMap[decade].years[year] || 0) + 1;
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
      .map(([year, count]) => ({
        year: parseInt(year),
        count
      }))
      .sort((a, b) => a.year - b.year);
  }, [albumsPerDecade]);

  /* ============================================================
     Bar Data (depends on chartMode)
  ============================================================ */

  const bars =
    chartMode === "decade"
      ? albumsPerDecade.map((d) => ({
          label: d.decade,
          count: d.count
        }))
      : allYears.map((y) => ({
          label: y.year,
          count: y.count
        }));

  const currentMax =
    bars.length > 0 ? Math.max(...bars.map((b) => b.count)) : 1;

  /* ============================================================
     Y-Axis Scaling (nice rounded ticks)
  ============================================================ */

  const tickCount = 5;
  const step = getNiceStep(currentMax, tickCount);
  const niceMax = Math.ceil(currentMax / step) * step;

  const tickValues = [];
  for (let i = 0; i <= niceMax; i += step) {
    tickValues.push(i);
  }

  /* ============================================================
     Bar Dimensions
  ============================================================ */

  const barWidth =
    bars.length > 0 ? innerWidth / bars.length - barGap : 0;

  /* ============================================================
     Render
  ============================================================ */

  return (
    <svg
      width={chartWidth}
      height={chartHeight}
      onClick={onReset} // clicking empty space resets filter
      style={{ cursor: "pointer" }}
    >
      {/* Shift entire chart into margin area */}
      <g transform={`translate(${margin.left}, ${margin.top})`}>
        {/* ======================================================
            Y-Axis
        ====================================================== */}
        <g>
          {tickValues.map((value, index) => {
            const y =
              innerHeight - (value / niceMax) * innerHeight;

            return (
              <g key={index} transform={`translate(0, ${y})`}>
                <line x1={0} x2={-5} y1={0} y2={0} stroke="#000" />
                <text
                  x={-10}
                  y={4}
                  textAnchor="end"
                  fontSize={10}
                >
                  {value}
                </text>
              </g>
            );
          })}

          {/* Y-axis line */}
          <line
            x1={0}
            y1={0}
            x2={0}
            y2={innerHeight}
            stroke="#000"
          />
        </g>

        {/* ======================================================
            X-Axis Baseline
        ====================================================== */}
        <line
          x1={0}
          y1={innerHeight}
          x2={innerWidth}
          y2={innerHeight}
          stroke="#000"
          strokeWidth={1.5}
        />

        {/* ======================================================
            Bars
        ====================================================== */}
        {bars.map((bar, index) => {
          const barHeight =
            (bar.count / niceMax) * innerHeight;

          const x = index * (barWidth + barGap);
          const y = innerHeight - barHeight;

          const isSelected =
            chartMode === "decade"
              ? selectedFilter.decade === bar.label
              : selectedFilter.year === bar.label;

          return (
            <g key={bar.label} transform={`translate(${x}, 0)`}>
              {/* Bar rectangle */}
              <rect
                x={0}
                y={y}
                width={barWidth}
                height={barHeight}
                fill={isSelected ? "orange" : "#4c78a8"}
                style={{ cursor: "pointer" }}
                onMouseEnter={() =>
                  setHoveredBar({
                    label: bar.label,
                    count: bar.count,
                    x: x + barWidth / 2,
                    y
                  })
                }
                onMouseLeave={() => setHoveredBar(null)}
                onClick={(e) => {
                  e.stopPropagation();

                  if (chartMode === "decade") {
                    onSelect(bar.label, null);
                  } else {
                    onSelect(
                      Math.floor(bar.label / 10) * 10,
                      bar.label
                    );
                  }
                }}
              />

              {/* X-axis labels
                 - Show all in decade mode
                 - Show every other in year mode
              */}
              {(chartMode === "decade" || index % 2 === 0) && (
                <text
                  x={barWidth / 2}
                  y={innerHeight + 12}
                  textAnchor="end"
                  fontSize={10}
                  transform={`rotate(-45, ${barWidth / 2}, ${
                    innerHeight + 12
                  })`}
                >
                  {bar.label}
                </text>
              )}
            </g>
          );
        })}

        {/* ======================================================
            Tooltip (rendered once)
        ====================================================== */}
        {hoveredBar && (
          <g
            transform={`translate(${hoveredBar.x}, ${
              hoveredBar.y - 10
            })`}
            pointerEvents="none"
          >
            <rect
              x={-45}
              y={-40}
              width={90}
              height={32}
              fill="white"
              stroke="#333"
              rx={4}
            />
            <text
              x={0}
              y={-25}
              textAnchor="middle"
              fontSize={10}
            >
              {chartMode === "decade" ? "Decade" : "Year"}:{" "}
              {hoveredBar.label}
            </text>
            <text
              x={0}
              y={-12}
              textAnchor="middle"
              fontSize={10}
            >
              Count: {hoveredBar.count}
            </text>
          </g>
        )}
      </g>
    </svg>
  );
}

export default ReleaseDateChart;