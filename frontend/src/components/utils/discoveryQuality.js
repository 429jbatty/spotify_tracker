const RANGE_DAYS = {
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

function getWindowStart(selectedRange, now) {
  if (selectedRange === "all") return new Date(0);

  const days = RANGE_DAYS[selectedRange] || RANGE_DAYS["7d"];
  return addDays(startOfDay(now), -(days - 1));
}

function normalizeIdentity(value) {
  return String(value || "")
    .trim()
    .toLocaleLowerCase()
    .replace(/\s+/g, " ");
}

function getAlbumKey(album) {
  if (album.album_key) return `key:${album.album_key}`;
  if (album.id != null) return `id:${album.id}`;
  if (album.release_group_mbid) return `release-group:${album.release_group_mbid}`;

  return `fallback:${normalizeIdentity(album.artist)}::${normalizeIdentity(album.name)}`;
}

function getAlbum(listen) {
  return listen.album || listen.albumMetadata || listen.metadata || listen;
}

function getListenDate(listen) {
  const value =
    listen.listenDate ||
    listen.listen_date ||
    listen.listened_at ||
    listen.date ||
    listen.timestamp;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function getScore(album) {
  const value =
    album.rating ??
    album.score ??
    album.user_score ??
    album.userScore ??
    album.ranking;
  const score = Number(value);

  return Number.isFinite(score) && score >= 0 && score <= 10 ? score : null;
}

function createScoreBuckets() {
  return Array.from({ length: 10 }, (_, index) => {
    const score = 10 - index;
    return {
      count: 0,
      key: String(score),
      label: `${score}/10`,
      score,
    };
  });
}

export function buildDiscoveryQuality(
  listens,
  selectedRange,
  { now: nowValue = new Date() } = {}
) {
  const now = new Date(nowValue);
  const windowStart = getWindowStart(selectedRange, now);
  const albumMap = new Map();

  (listens || []).forEach((listen) => {
    const date = getListenDate(listen);
    if (!date || date.getTime() > now.getTime()) return;

    const album = getAlbum(listen);
    const key = getAlbumKey(album);
    const current = albumMap.get(key);
    if (!current || date.getTime() < current.firstListen.getTime()) {
      albumMap.set(key, { album, firstListen: date });
    }
  });

  const discoveries = [...albumMap.values()].filter(
    (record) => record.firstListen.getTime() >= windowStart.getTime()
  );
  const buckets = createScoreBuckets();
  const ratedScores = [];
  let unratedDiscoveries = 0;

  discoveries.forEach(({ album }) => {
    const score = getScore(album);
    if (score == null) {
      unratedDiscoveries += 1;
      return;
    }

    const roundedScore = Math.round(score);
    const bucket = buckets.find((item) => item.score === roundedScore);
    if (bucket) bucket.count += 1;
    ratedScores.push(score);
  });

  const ratedDiscoveries = ratedScores.length;
  const greatCount = ratedScores.filter((score) => score >= 8).length;
  const averageScore =
    ratedDiscoveries === 0
      ? null
      : ratedScores.reduce((sum, score) => sum + score, 0) / ratedDiscoveries;

  return {
    averageScore,
    buckets,
    percentGreat:
      ratedDiscoveries === 0 ? null : (greatCount / ratedDiscoveries) * 100,
    ratedDiscoveries,
    totalDiscoveries: discoveries.length,
    unratedDiscoveries,
  };
}
