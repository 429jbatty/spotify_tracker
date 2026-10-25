const RANGE_DAYS = {
  "7d": 7,
  "30d": 30,
  "1y": 365,
};

function normalizeIdentity(value) {
  return String(value || "")
    .trim()
    .toLocaleLowerCase()
    .replace(/\s+/g, " ");
}

function getArtistKey(album) {
  return album.artist_mbid
    ? `mbid:${album.artist_mbid}`
    : `name:${normalizeIdentity(album.artist)}`;
}

function getAlbumKey(album) {
  if (album.album_key) return `key:${album.album_key}`;
  if (album.id != null) return `id:${album.id}`;
  if (album.release_group_mbid) return `release-group:${album.release_group_mbid}`;

  return `fallback:${normalizeIdentity(album.artist)}::${normalizeIdentity(album.name)}`;
}

function startOfDay(value) {
  const date = new Date(value);
  date.setHours(0, 0, 0, 0);
  return date;
}

function startOfWeek(value) {
  const date = startOfDay(value);
  const mondayOffset = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - mondayOffset);
  return date;
}

function addDays(value, days) {
  const date = new Date(value);
  date.setDate(date.getDate() + days);
  return date;
}

function minDate(left, right) {
  return left.getTime() <= right.getTime() ? left : right;
}

function maxDate(left, right) {
  return left.getTime() >= right.getTime() ? left : right;
}

function formatShortDate(date, includeYear = false) {
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    ...(includeYear ? { year: "numeric" } : {}),
  });
}

function getWindowStart(timeRange, now) {
  const days = RANGE_DAYS[timeRange] || RANGE_DAYS["7d"];
  return addDays(startOfDay(now), -(days - 1));
}

function getPreviousWindow(timeRange, windowStart) {
  const days = RANGE_DAYS[timeRange];
  if (!days) return null;

  return {
    endExclusive: windowStart,
    start: addDays(windowStart, -days),
  };
}

function getBucketConfig(timeRange) {
  if (timeRange === "7d" || timeRange === "30d") {
    return { start: startOfDay, next: (date) => addDays(date, 1) };
  }

  return { start: startOfWeek, next: (date) => addDays(date, 7) };
}

function summarizeEvents(events, windowStart, windowEndExclusive) {
  return events.reduce(
    (totals, event) => ({
      newToYou:
        totals.newToYou +
        (event.firstAlbumListenAt >= windowStart.getTime() &&
        event.firstAlbumListenAt < windowEndExclusive.getTime()
          ? 1
          : 0),
      catalog: totals.catalog +
        (event.firstAlbumListenAt >= windowStart.getTime() &&
        event.firstAlbumListenAt < windowEndExclusive.getTime()
          ? 0
          : 1),
      totalListens: totals.totalListens + 1,
    }),
    { newToYou: 0, catalog: 0, totalListens: 0 }
  );
}

function collectAlbumRecords(albums) {
  return Object.values(albums || {}).map((album) => {
    const artistKey = getArtistKey(album);
    const albumKey = getAlbumKey(album);
    const listenDates = (album.listen_history || [])
      .map((dateValue) => new Date(dateValue))
      .filter((date) => !Number.isNaN(date.getTime()))
      .sort((left, right) => left.getTime() - right.getTime());

    return {
      album,
      albumKey,
      artistKey,
      artistName: album.artist || "Unknown artist",
      listenDates,
      releaseYear: Number.isInteger(album.release_year) ? album.release_year : null,
    };
  });
}

function collectListenEvents(albumRecords) {
  const events = albumRecords.flatMap((record) =>
    record.listenDates.map((date) => ({
      albumKey: record.albumKey,
      artistKey: record.artistKey,
      artistName: record.artistName,
      date,
      releaseYear: record.releaseYear,
      timestamp: date.getTime(),
    }))
  );

  events.sort(
    (left, right) =>
      left.timestamp - right.timestamp ||
      left.artistKey.localeCompare(right.artistKey) ||
      left.albumKey.localeCompare(right.albumKey)
  );

  const firstAlbumListenAt = new Map();
  const seenAlbums = new Set();
  const seenArtists = new Set();

  return events.map((event) => {
    const isFirstArtistListen = !seenArtists.has(event.artistKey);
    const isFirstAlbumListen = !seenAlbums.has(event.albumKey);
    if (isFirstAlbumListen) firstAlbumListenAt.set(event.albumKey, event.timestamp);

    seenArtists.add(event.artistKey);
    seenAlbums.add(event.albumKey);

    return {
      ...event,
      firstAlbumListenAt: firstAlbumListenAt.get(event.albumKey),
      isFirstAlbumListen,
      isFirstArtistListen,
    };
  });
}

function createBuckets(timeRange, windowStart, now) {
  const { start, next } = getBucketConfig(timeRange);
  const firstBucketStart = start(windowStart);
  const lastBucketStart = start(now);
  const buckets = [];

  for (
    let bucketStart = firstBucketStart;
    bucketStart.getTime() <= lastBucketStart.getTime();
    bucketStart = next(bucketStart)
  ) {
    const followingStart = next(bucketStart);
    const displayStart = maxDate(bucketStart, windowStart);
    const displayEnd = minDate(addDays(followingStart, -1), startOfDay(now));
    const includeYear = displayStart.getFullYear() !== now.getFullYear();
    const label = formatShortDate(displayStart, includeYear);
    const rangeLabel = displayStart.getTime() === displayEnd.getTime()
      ? formatShortDate(displayStart, true)
      : `${formatShortDate(displayStart, true)} – ${formatShortDate(displayEnd, true)}`;

    buckets.push({
      start: bucketStart,
      endExclusive: followingStart,
      label,
      rangeLabel,
      newToYou: 0,
      catalog: 0,
      total: 0,
      percentages: { newToYou: 0, catalog: 0 },
      catalogAlbums: 0,
      catalogArtists: 0,
      albumGrowth: 0,
      artistGrowth: 0,
    });
  }

  return buckets;
}

function getTopFiveShare(events) {
  if (events.length === 0) return 0;

  const artistCounts = new Map();
  events.forEach((event) => {
    artistCounts.set(event.artistKey, (artistCounts.get(event.artistKey) || 0) + 1);
  });
  const topFiveTotal = [...artistCounts.values()]
    .sort((left, right) => right - left)
    .slice(0, 5)
    .reduce((total, count) => total + count, 0);

  return (topFiveTotal / events.length) * 100;
}

function buildConcentrationSeries(buckets, events, windowStart, windowEndExclusive) {
  return buckets.map((bucket) => {
    const periodEvents = events.filter(
      (event) =>
        event.date.getTime() >= Math.max(bucket.start.getTime(), windowStart.getTime()) &&
        event.date.getTime() < Math.min(
          bucket.endExclusive.getTime(),
          windowEndExclusive.getTime()
        )
    );

    return {
      label: bucket.label,
      rangeLabel: bucket.rangeLabel,
      share: periodEvents.length === 0 ? null : getTopFiveShare(periodEvents),
      total: periodEvents.length,
    };
  });
}

function buildArtistMap(events) {
  const artistMap = new Map();

  events.forEach((event) => {
    if (!artistMap.has(event.artistKey)) {
      artistMap.set(event.artistKey, {
        albumKeys: new Set(),
        artist: event.artistName,
        listenCount: 0,
      });
    }

    const artist = artistMap.get(event.artistKey);
    artist.albumKeys.add(event.albumKey);
    artist.listenCount += 1;
  });

  return [...artistMap.values()]
    .map((artist) => ({
      albumCount: artist.albumKeys.size,
      artist: artist.artist,
      listenCount: artist.listenCount,
    }))
    .sort(
      (left, right) =>
        right.listenCount - left.listenCount ||
        right.albumCount - left.albumCount ||
        left.artist.localeCompare(right.artist)
    );
}

function buildTrendSeries(buckets) {
  return buckets.map((bucket) => ({
    newToYou: bucket.newToYou,
    label: bucket.label,
    rangeLabel: bucket.rangeLabel,
    catalog: bucket.catalog,
    total: bucket.total,
  }));
}

export function aggregateDiscoveryInsights(
  albums,
  timeRange,
  { now: nowValue = new Date() } = {}
) {
  const now = new Date(nowValue);
  const albumRecords = collectAlbumRecords(albums);
  const events = collectListenEvents(albumRecords);
  const windowStart = getWindowStart(timeRange, now);
  const windowEndExclusive = new Date(now.getTime() + 1);
  const buckets = createBuckets(timeRange, windowStart, now);
  const catalogAlbums = new Set();
  const catalogArtists = new Set();
  let eventIndex = 0;

  while (
    eventIndex < events.length &&
    events[eventIndex].date.getTime() < windowStart.getTime()
  ) {
    catalogAlbums.add(events[eventIndex].albumKey);
    catalogArtists.add(events[eventIndex].artistKey);
    eventIndex += 1;
  }

  const baseline = {
    albums: catalogAlbums.size,
    artists: catalogArtists.size,
  };

  buckets.forEach((bucket) => {
    while (
      eventIndex < events.length &&
      events[eventIndex].date.getTime() < bucket.endExclusive.getTime() &&
      events[eventIndex].date.getTime() < windowEndExclusive.getTime()
    ) {
      const event = events[eventIndex];

      if (event.date.getTime() >= windowStart.getTime()) {
        const isNewToYou =
          event.firstAlbumListenAt >= windowStart.getTime() &&
          event.firstAlbumListenAt < windowEndExclusive.getTime();
        bucket[isNewToYou ? "newToYou" : "catalog"] += 1;
        bucket.total += 1;
        if (event.isFirstAlbumListen) bucket.albumGrowth += 1;
        if (event.isFirstArtistListen) bucket.artistGrowth += 1;
      }

      catalogAlbums.add(event.albumKey);
      catalogArtists.add(event.artistKey);
      eventIndex += 1;
    }

    bucket.catalogAlbums = catalogAlbums.size;
    bucket.catalogArtists = catalogArtists.size;

    if (bucket.total > 0) {
      bucket.percentages = {
        newToYou: (bucket.newToYou / bucket.total) * 100,
        catalog: (bucket.catalog / bucket.total) * 100,
      };
    }
  });

  const summary = buckets.reduce(
    (totals, bucket) => ({
      newToYou: totals.newToYou + bucket.newToYou,
      catalog: totals.catalog + bucket.catalog,
      totalListens: totals.totalListens + bucket.total,
    }),
    { newToYou: 0, catalog: 0, totalListens: 0 }
  );
  const windowEvents = events.filter(
    (event) =>
      event.date.getTime() >= windowStart.getTime() &&
      event.date.getTime() < windowEndExclusive.getTime()
  );
  const previousWindow = getPreviousWindow(timeRange, windowStart);
  const previousEvents = previousWindow
    ? events.filter(
        (event) =>
          event.date.getTime() >= previousWindow.start.getTime() &&
          event.date.getTime() < previousWindow.endExclusive.getTime()
      )
    : [];

  return {
    artistMap: buildArtistMap(windowEvents),
    baseline,
    buckets,
    concentration: {
      overallShare: getTopFiveShare(windowEvents),
      series: buildConcentrationSeries(
        buckets,
        events,
        windowStart,
        windowEndExclusive
      ),
    },
    coverage: {
      datedAlbums: albumRecords.filter((record) => record.listenDates.length > 0).length,
      totalAlbums: albumRecords.length,
    },
    previousPeriod: previousWindow
      ? {
          concentration: {
            overallShare: getTopFiveShare(previousEvents),
          },
          summary: summarizeEvents(
            previousEvents,
            previousWindow.start,
            previousWindow.endExclusive
          ),
          windowStart: previousWindow.start,
          windowEndExclusive: previousWindow.endExclusive,
        }
      : null,
    summary,
    totalLifetimeListens: events.filter(
      (event) => event.date.getTime() < windowEndExclusive.getTime()
    ).length,
    trendSeries: buildTrendSeries(buckets),
    windowStart,
  };
}
