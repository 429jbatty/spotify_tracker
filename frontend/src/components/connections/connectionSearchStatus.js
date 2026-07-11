export function connectionSearchProgress(elapsedSeconds) {
  const elapsed = Math.max(0, elapsedSeconds || 0);
  return {
    detail: elapsed >= 5
      ? "This library search is taking longer than usual."
      : "Checking direct and indirect credit paths.",
    label: `Searching your credit network… ${elapsed}s`,
  };
}

export function connectionSearchResult(connection) {
  const hasPath = Boolean(connection?.best_path);
  const limitedReason = connection?.search_limited_reason;

  if (hasPath && limitedReason === "time_limit") {
    return {
      detail: "A path was confirmed, but the time limit was reached before every alternative could be checked.",
      title: "Indirect credit path",
    };
  }
  if (hasPath && limitedReason === "result_limit") {
    return {
      detail: "The strongest paths found within the result limit are shown.",
      title: connection.best_path.hop_count === 1 ? "Direct shared credits" : "Indirect credit path",
    };
  }
  if (!hasPath && limitedReason === "time_limit") {
    const seconds = Math.round((connection?.search_time_limit_ms || 0) / 1000);
    return {
      detail: `No path was confirmed before the ${seconds || 20}-second search limit. Try another pair or come back later.`,
      title: "Search limit reached",
    };
  }
  if (!hasPath && ["edge_limit", "expansion_limit", "queue_limit", "state_limit"].includes(limitedReason)) {
    return {
      detail: "This library is highly connected, so the search stopped before every route could be checked. Try another pair or come back later.",
      title: "Search limit reached",
    };
  }
  if (hasPath && ["edge_limit", "expansion_limit", "queue_limit", "state_limit"].includes(limitedReason)) {
    return {
      detail: "A path was confirmed, but the library search stopped before every alternative could be checked.",
      title: "Indirect credit path",
    };
  }
  if (hasPath) {
    return {
      detail: null,
      title: connection.best_path.hop_count === 1 ? "Direct shared credits" : "Indirect credit path",
    };
  }
  return {
    detail: null,
    title: "No reliable path found",
  };
}
