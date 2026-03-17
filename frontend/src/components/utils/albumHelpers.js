export function groupAlbumCredits(album) {
  const categories = {
    Engineers: ["engineer", "mix"],
    Instrumentation: ["instrument"],
    Producer: ["producer"],
    Other: [],
  };

  const grouped = {
    Engineers: {},
    Instrumentation: {},
    Producer: {},
    Other: {},
  };

  for (const track of album.tracklist || []) {
    const credits = Array.isArray(track.credits) ? track.credits : [];

    for (const credit of credits) {
      if (!Array.isArray(credit) || credit.length < 3) continue;

      const [name, role, detail] = credit;
      const roleDetail = detail ? `${role}, ${detail}` : role;

      let category = "Other";

      for (const [catName, roles] of Object.entries(categories)) {
        if (roles.includes(role.toLowerCase())) {
          category = catName;
          break;
        }
      }

      if (!grouped[category][name]) grouped[category][name] = new Set();
      grouped[category][name].add(roleDetail);
    }
  }

  for (const category of Object.keys(grouped)) {
    for (const person of Object.keys(grouped[category])) {
      grouped[category][person] = Array.from(grouped[category][person]);
    }
  }

  return grouped;
}

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