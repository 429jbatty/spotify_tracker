const FALLBACKS = {
  "--chart-1": "#f3cc39",
  "--chart-2": "#eda72d",
  "--chart-3": "#d77825",
  "--chart-4": "#b95621",
  "--chart-5": "#8d3f1e",
  "--foreground": "#252525",
  "--muted-foreground": "#737373",
};

export function getChartColor(property) {
  if (typeof document === "undefined") return FALLBACKS[property];

  return (
    getComputedStyle(document.documentElement).getPropertyValue(property).trim() ||
    FALLBACKS[property]
  );
}
