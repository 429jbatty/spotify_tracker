# MusicBrainz Resolver Benchmark

Use this benchmark when you want to see whether the current bounded
MusicBrainz resolver is selecting better metadata than the previous one-shot
lookup.

Run it from the repo root:

```bash
./.venv/bin/python one_time_scripts/_benchmark_musicbrainz_resolver.py
```

Optional JSON output:

```bash
./.venv/bin/python one_time_scripts/_benchmark_musicbrainz_resolver.py \
  --json-output data/musicbrainz_resolver_benchmark.json
```

## What It Measures

The benchmark uses fixed mocked MusicBrainz fixtures. It does not call the live
MusicBrainz API.

For each fixture, it runs:

- `legacy`: a local copy of the old one-shot release-group selection flow.
- `current`: `musicbrainz_resolver.resolve_musicbrainz_candidate(...)`.

It reports:

- selected release-group MBID
- expected release-group MBID
- current resolver confidence
- whether the current result would auto-apply at the canonical refresh threshold
- wrapper-call counts for search, release-group lookup, release browsing, full
  release loading, and cover art lookup
- aggregate selection accuracy and safe auto-apply decisions

## How To Interpret It

The current resolver is intentionally more thorough. On ambiguous cases it may
make more MusicBrainz wrapper calls than the legacy one-shot flow because it
evaluates multiple release groups and releases before choosing metadata.

The important metrics are:

- `Selection accuracy`: whether the selected release group is the expected one.
- `Auto-apply decisions`: whether the resolver would automatically write the
  metadata only when it should.
- `Fixture API calls`: the bounded lookup cost. This is a local wrapper-call
  count, not live network latency.
- `Correct decisions per fixture call`: a rough accuracy-per-cost signal.

If accuracy improves but calls increase, that is expected for this resolver.
Use the call counts to watch for accidental unbounded behavior, not as proof
that every individual lookup is faster.

## Expanding The Fixture Set

Add new cases to `benchmark_cases()` in
`one_time_scripts/_benchmark_musicbrainz_resolver.py` when you find another
real-world lookup that behaves badly.

Good benchmark cases have:

- an input artist and album
- an expected release-group MBID
- competing release groups that explain the ambiguity
- release summaries and full releases for every candidate that should be
  evaluated
- an `expected_auto_apply` value that says whether the result is safe to write
  automatically

Keep this benchmark mocked. Live MusicBrainz tests should remain opt-in behind
`RUN_LIVE_MUSICBRAINZ_TESTS=1`.
