export function getListenStats(history = []) {
  if (!history.length) return null;

  const dates = history.map((d) => new Date(d)).sort((a, b) => a - b);

  return {
    count: dates.length,
    first: dates[0],
    last: dates[dates.length - 1],
  };
}

export function formatDate(date) {
  if (!date) return null;

  return date.toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
  });
}

export function buildSparkline(history = [], buckets = 12) {
  if (history.length < 3) return Array(buckets).fill(0);

  const dates = history.map((d) => new Date(d)).sort((a, b) => a - b);
  const start = dates[0].getTime();
  const end = dates[dates.length - 1].getTime();
  const span = end - start || 1;

  const counts = Array(buckets).fill(0);

  for (const date of dates) {
    const position = Math.floor(
      ((date.getTime() - start) / span) * (buckets - 1)
    );
    counts[position]++;
  }

  return counts;
}