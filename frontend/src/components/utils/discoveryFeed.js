const TIME_RANGE_DAYS = {
  "7d": 7,
  "30d": 30,
  "1y": 365,
};

function addDays(value, days) {
  const date = new Date(value);
  date.setDate(date.getDate() + days);
  return date;
}

function startOfDay(value) {
  const date = new Date(value);
  date.setHours(0, 0, 0, 0);
  return date;
}

function getRangeStart(timeRange, now) {
  const days = TIME_RANGE_DAYS[timeRange] || TIME_RANGE_DAYS["7d"];
  return addDays(startOfDay(now), -(days - 1));
}

function parseListenDates(album) {
  return (album.listen_history || [])
    .map((dateValue) => new Date(dateValue))
    .filter((date) => !Number.isNaN(date.getTime()))
    .sort((left, right) => left.getTime() - right.getTime());
}

function formatDiscoveryDate(value) {
  return value.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function buildDiscoveryFeed(albums, timeRange, { now: nowValue = new Date() } = {}) {
  const now = new Date(nowValue);
  const rangeStart = getRangeStart(timeRange, now);

  return Object.values(albums || {})
    .map((album) => {
      const listenDates = parseListenDates(album);
      const firstListen = listenDates[0] || null;
      const inRangeListens = listenDates.filter(
        (date) =>
          date.getTime() >= rangeStart.getTime() &&
          date.getTime() <= now.getTime()
      );
      const latestInRangeListen = inRangeListens[inRangeListens.length - 1] || null;
      const discoveredInRange =
        firstListen != null &&
        firstListen.getTime() >= rangeStart.getTime() &&
        firstListen.getTime() <= now.getTime();
      const latestIsDiscovery =
        firstListen != null &&
        latestInRangeListen != null &&
        firstListen.getTime() === latestInRangeListen.getTime();
      const highlightDiscovery = discoveredInRange;

      return {
        ...album,
        discoveredInRange,
        discoveryLabel: discoveredInRange
          ? latestIsDiscovery
            ? "New discovery"
            : `Discovered ${formatDiscoveryDate(firstListen)}`
          : null,
        firstListenDate: firstListen?.toISOString() || null,
        firstListenTime: firstListen?.getTime() || null,
        highlightDiscovery,
        inRangeListenCount: inRangeListens.length,
        latestInRangeListen: latestInRangeListen?.toISOString() || null,
        latestInRangeListenTime: latestInRangeListen?.getTime() || null,
      };
    })
    .filter((album) => album.latestInRangeListenTime != null)
    .sort(
      (left, right) =>
        right.latestInRangeListenTime - left.latestInRangeListenTime ||
        String(left.artist || "").localeCompare(String(right.artist || "")) ||
        String(left.name || "").localeCompare(String(right.name || ""))
    );
}
