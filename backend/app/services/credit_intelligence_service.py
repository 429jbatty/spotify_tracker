import re
import time
import unicodedata
from collections import Counter, deque
from dataclasses import dataclass, field
from itertools import combinations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import Album, AlbumCreditFact, User, UserAlbum


DEFAULT_EXCLUDED_FLAGS = {
    "primary_artist_candidate",
    "unresolved_identity",
    "generic_instrument",
}
DEFAULT_EXCLUDED_ROLE_BUCKETS = {"primary_artist"}
DEFAULT_EXCLUDED_NORMALIZED_NAMES = {
    "[traditional]",
    "traditional",
    "[unknown]",
    "unknown",
    "anonymous",
}
MIN_ALBUMS_FOR_RECURRING = 2
MIN_PRIMARY_ARTISTS_FOR_RECURRING = 2
MIN_ALBUMS_WITH_FACTS_FOR_CONFIDENT_RESULTS = 5
ALBUM_PAIR_ROLE_BUCKETS = {
    "producer",
    "writer_composer",
    "mixing_mastering",
    "engineering",
    "performer",
}
GRAPH_ROLE_BUCKETS = ALBUM_PAIR_ROLE_BUCKETS
ARTWORK_URL_PREFIX = "/media/artwork/"
MAX_ALBUM_CONNECTION_CONTRIBUTOR_HOPS = 4
MAX_ALBUM_CONNECTION_ALTERNATES = 3
MAX_ALBUM_CONNECTION_PATHS = 1 + MAX_ALBUM_CONNECTION_ALTERNATES
MAX_ALBUM_CONNECTION_SEARCH_SECONDS = 5
MAX_ALBUM_CONNECTION_SEARCH_STATES = 10_000
MAX_ALBUM_CONNECTION_SEARCH_EDGES = 50_000
MAX_ALBUM_CONNECTION_SEARCH_QUEUE_SIZE = 20_000
MAX_ALBUM_CONNECTION_ALBUMS_PER_CONTRIBUTOR = 250


@dataclass
class AlbumFactSummary:
    album_id: int
    album_key: str
    artist: str
    name: str
    artist_mbid: str | None
    image_url: str | None = None
    role_buckets: Counter[str] = field(default_factory=Counter)
    raw_roles: Counter[str] = field(default_factory=Counter)
    quality_flags: set[str] = field(default_factory=set)
    identity_resolution: set[str] = field(default_factory=set)
    ingestion_versions: set[str] = field(default_factory=set)


@dataclass
class ContributorSummary:
    person_key: str
    person_name: str
    person_mbid: str | None
    album_ids: set[int] = field(default_factory=set)
    artist_keys: set[str] = field(default_factory=set)
    role_buckets: Counter[str] = field(default_factory=Counter)
    raw_roles: Counter[str] = field(default_factory=Counter)
    quality_flags: set[str] = field(default_factory=set)
    identity_resolution: set[str] = field(default_factory=set)
    ingestion_versions: set[str] = field(default_factory=set)
    albums: dict[int, AlbumFactSummary] = field(default_factory=dict)


@dataclass
class AlbumPairFactSummary:
    album: AlbumFactSummary
    track_count: int = 0
    role_buckets: Counter[str] = field(default_factory=Counter)
    raw_roles: Counter[str] = field(default_factory=Counter)
    quality_flags: set[str] = field(default_factory=set)
    identity_resolution: set[str] = field(default_factory=set)
    ingestion_versions: set[str] = field(default_factory=set)


@dataclass
class AlbumCreditPairSummary:
    album_a: AlbumPairFactSummary
    album_b: AlbumPairFactSummary
    person_key: str
    person_name: str
    person_mbid: str | None
    role_bucket: str
    raw_roles: Counter[str] = field(default_factory=Counter)
    quality_flags: set[str] = field(default_factory=set)
    identity_resolution: set[str] = field(default_factory=set)
    ingestion_versions: set[str] = field(default_factory=set)

    @property
    def evidence_track_count(self) -> int:
        return self.album_a.track_count + self.album_b.track_count

    @property
    def cross_primary_artist(self) -> bool:
        return _artist_key(self.album_a.album.artist, self.album_a.album.artist_mbid) != _artist_key(
            self.album_b.album.artist, self.album_b.album.artist_mbid
        )


@dataclass
class AlbumConnectionStep:
    contributor: ContributorSummary
    from_album_id: int
    to_album_id: int
    role_bucket: str


@dataclass
class AlbumConnectionPath:
    steps: list[AlbumConnectionStep]

    @property
    def contributor_keys(self) -> list[str]:
        return [step.contributor.person_key for step in self.steps]

    @property
    def album_ids(self) -> list[int]:
        if not self.steps:
            return []
        album_ids = [self.steps[0].from_album_id]
        album_ids.extend(step.to_album_id for step in self.steps)
        return album_ids

    @property
    def hop_count(self) -> int:
        return len(self.steps)


@dataclass
class AlbumConnectionPathSearch:
    paths: list[AlbumConnectionPath]
    limited: bool = False
    limited_reason: str | None = None
    states_examined: int = 0
    edges_examined: int = 0
    max_queue_size: int = 0


@dataclass(frozen=True)
class CreditConnectionGraph:
    contributors_by_album: dict[int, tuple[ContributorSummary, ...]]


def recurring_contributors(
    session: Session,
    user_slug: str,
    *,
    limit: int = 25,
) -> dict:
    user = _require_user(session, user_slug)
    coverage = _coverage(session, user.id)
    ranked = _eligible_recurring_contributors(session, user.id)
    limited = ranked[:limit]

    return {
        "user_slug": user.slug,
        "coverage": coverage,
        "results": [_contributor_payload(contributor) for contributor in limited],
        "insufficient_data_reason": _insufficient_data_reason(coverage, limited),
    }


def search_recurring_contributors(
    session: Session,
    user_slug: str,
    *,
    query: str = "",
    limit: int = 25,
    offset: int = 0,
) -> dict:
    user = _require_user(session, user_slug)
    terms = _search_terms(query)
    matches = [
        contributor
        for contributor in _eligible_recurring_contributors(session, user.id)
        if _contributor_matches_search(contributor, terms)
    ]
    page = matches[offset : offset + limit]

    return {
        "user_slug": user.slug,
        "query": query,
        "offset": offset,
        "limit": limit,
        "total": len(matches),
        "results": [_contributor_payload(contributor) for contributor in page],
    }


def person_detail(session: Session, user_slug: str, person_key: str) -> dict:
    user = _require_user(session, user_slug)
    rows = [
        row
        for row in _user_fact_rows(session, user.id)
        if row["person_key"] == person_key
    ]
    if not rows:
        raise KeyError(f"Contributor not found for user: {person_key}")

    contributors = _aggregate_contributors(rows, exclude_default_noise=False)
    contributor = contributors[person_key]
    return {
        **_contributor_payload(contributor),
        "albums": [_album_payload(album) for album in _rank_albums(contributor)],
    }


def suggested_album_pairs(
    session: Session,
    user_slug: str,
    *,
    limit: int = 12,
) -> dict:
    user = _require_user(session, user_slug)
    coverage = _coverage(session, user.id)
    rows = _user_fact_rows(session, user.id)
    pairs = _build_album_pairs(rows)
    pairs.sort(key=_album_pair_sort_key)
    limited = pairs[:limit]

    return {
        "user_slug": user.slug,
        "coverage": coverage,
        "results": [_album_pair_payload(pair) for pair in limited],
        "insufficient_data_reason": _insufficient_data_reason(coverage, limited),
    }


def connection_graph(
    session: Session,
    user_slug: str,
    *,
    contributor_limit: int = 12,
    album_limit_per_contributor: int = 6,
    album_limit: int = 48,
    focus_node_id: str | None = None,
) -> dict:
    user = _require_user(session, user_slug)
    coverage = _coverage(session, user.id)
    rows = _user_fact_rows(session, user.id)
    contributors = _aggregate_contributors(rows, exclude_default_noise=True)
    ranked = [
        contributor
        for contributor in contributors.values()
        if len(contributor.album_ids) >= MIN_ALBUMS_FOR_RECURRING
        and len(contributor.artist_keys) >= MIN_PRIMARY_ARTISTS_FOR_RECURRING
        and any(role in GRAPH_ROLE_BUCKETS for role in contributor.role_buckets)
    ]
    ranked.sort(key=_contributor_sort_key)
    selected = _focused_graph_contributors(ranked, focus_node_id, contributor_limit)
    nodes, edges = _graph_payload(selected, album_limit_per_contributor, album_limit)

    return {
        "user_slug": user.slug,
        "coverage": coverage,
        "nodes": nodes,
        "edges": edges,
        "insufficient_data_reason": _insufficient_data_reason(coverage, nodes),
    }


def album_connection_graph(
    session: Session,
    user_slug: str,
    *,
    album_a_id: int,
    album_b_id: int,
) -> dict:
    started_at = time.monotonic()
    deadline = started_at + MAX_ALBUM_CONNECTION_SEARCH_SECONDS
    if album_a_id == album_b_id:
        raise ValueError("Choose two different albums.")

    user = _require_user(session, user_slug)
    coverage = _coverage(session, user.id)
    album_ids = _require_user_album_ids(session, user.id, {album_a_id, album_b_id})
    all_rows = _user_fact_rows(session, user.id)
    rows = [row for row in all_rows if row["fact"].album_id in album_ids]
    album_summaries = _user_album_summaries(session, user.id, album_ids)
    for album_id, summary in _album_summaries_from_rows(rows).items():
        album_summaries[album_id] = summary
    contributors = _direct_album_connection_contributors(rows, album_a_id, album_b_id)
    graph_build_ms = 0
    if contributors:
        direct_paths = [
            AlbumConnectionPath(steps=[
                AlbumConnectionStep(
                    contributor=contributor,
                    from_album_id=album_a_id,
                    to_album_id=album_b_id,
                    role_bucket=_connection_step_role(contributor, album_a_id, album_b_id),
                )
            ])
            for contributor in contributors[:MAX_ALBUM_CONNECTION_PATHS]
        ]
        path_search = AlbumConnectionPathSearch(
            paths=direct_paths,
            limited=len(contributors) > MAX_ALBUM_CONNECTION_PATHS,
            limited_reason=(
                "result_limit" if len(contributors) > MAX_ALBUM_CONNECTION_PATHS else None
            ),
        )
    elif time.monotonic() >= deadline:
        path_search = AlbumConnectionPathSearch(paths=[], limited=True, limited_reason="time_limit")
    else:
        graph_build_started_at = time.monotonic()
        connection_graph = _prepare_album_connection_graph(all_rows)
        graph_build_ms = round((time.monotonic() - graph_build_started_at) * 1000)
        path_search = _album_connection_paths(
            connection_graph,
            album_a_id,
            album_b_id,
            deadline=deadline,
        )
    paths = path_search.paths
    path_album_ids = {album_id for path in paths for album_id in path.album_ids}
    if path_album_ids:
        album_summaries.update(_album_summaries_from_rows([row for row in all_rows if row["fact"].album_id in path_album_ids]))
        missing_album_ids = path_album_ids - set(album_summaries)
        if missing_album_ids:
            album_summaries.update(_user_album_summaries(session, user.id, missing_album_ids))
    nodes, edges = _album_connection_graph_payload(
        contributors,
        album_a_id,
        album_b_id,
        album_summaries,
        best_path=paths[0] if paths else None,
    )
    album_a = album_summaries[album_a_id]
    album_b = album_summaries[album_b_id]
    shared = [_album_connection_contributor_payload(item, album_a_id, album_b_id) for item in contributors]

    search_elapsed_ms = round((time.monotonic() - started_at) * 1000)
    return {
        "user_slug": user.slug,
        "coverage": coverage,
        "album_a": _album_payload(album_a),
        "album_b": _album_payload(album_b),
        "nodes": nodes,
        "edges": edges,
        "shared_contributors": shared,
        "best_path": _album_connection_path_payload(paths[0], album_summaries) if paths else None,
        "alternate_paths": [
            _album_connection_path_payload(path, album_summaries)
            for path in paths[1 : MAX_ALBUM_CONNECTION_ALTERNATES + 1]
        ],
        "no_direct_connection": len(shared) == 0,
        "no_path": not path_search.limited and len(paths) == 0,
        "max_contributor_hops": MAX_ALBUM_CONNECTION_CONTRIBUTOR_HOPS,
        "search_status": "limited" if path_search.limited else "complete",
        "search_limited_reason": path_search.limited_reason,
        "search_elapsed_ms": search_elapsed_ms,
        "search_time_limit_ms": MAX_ALBUM_CONNECTION_SEARCH_SECONDS * 1000,
        "search_graph_build_ms": graph_build_ms,
        "search_states_examined": path_search.states_examined,
        "search_edges_examined": path_search.edges_examined,
        "search_max_queue_size": path_search.max_queue_size,
        "insufficient_data_reason": _insufficient_data_reason(coverage, nodes),
    }


def _focused_graph_contributors(
    ranked: list[ContributorSummary],
    focus_node_id: str | None,
    contributor_limit: int,
) -> list[ContributorSummary]:
    if not focus_node_id:
        return ranked[:contributor_limit]

    focused: list[ContributorSummary] = []
    if focus_node_id.startswith("contributor:"):
        person_key = focus_node_id.removeprefix("contributor:")
        focused = [
            contributor
            for contributor in ranked
            if contributor.person_key == person_key
        ]
    elif focus_node_id.startswith("album:"):
        album_id = _parse_graph_album_focus(focus_node_id)
        if album_id is not None:
            focused = [
                contributor
                for contributor in ranked
                if album_id in contributor.album_ids
            ]

    selected: list[ContributorSummary] = []
    seen = set()
    for contributor in [*focused, *ranked]:
        if contributor.person_key in seen:
            continue
        seen.add(contributor.person_key)
        selected.append(contributor)
        if len(selected) >= contributor_limit:
            break
    return selected


def _parse_graph_album_focus(focus_node_id: str) -> int | None:
    try:
        return int(focus_node_id.removeprefix("album:"))
    except ValueError:
        return None


def _require_user_album_ids(session: Session, user_id: int, album_ids: set[int]) -> set[int]:
    owned_ids = set(
        session.scalars(
            select(UserAlbum.album_id)
            .where(UserAlbum.user_id == user_id)
            .where(UserAlbum.album_id.in_(album_ids))
        ).all()
    )
    if owned_ids != album_ids:
        missing = sorted(album_ids - owned_ids)
        raise KeyError(f"Album not found for user library: {missing}")
    return owned_ids


def _user_album_summaries(
    session: Session,
    user_id: int,
    album_ids: set[int],
) -> dict[int, AlbumFactSummary]:
    rows = session.execute(
        select(
            Album.id,
            Album.album_key,
            Album.artist,
            Album.name,
            Album.artist_mbid,
            Album.image_url,
            Album.local_image_path,
        )
        .join(UserAlbum, UserAlbum.album_id == Album.id)
        .where(UserAlbum.user_id == user_id)
        .where(Album.id.in_(album_ids))
    ).all()
    return {
        album_id: AlbumFactSummary(
            album_id=album_id,
            album_key=album_key,
            artist=artist,
            name=name,
            artist_mbid=artist_mbid,
            image_url=_display_image_url(image_url, local_image_path),
        )
        for album_id, album_key, artist, name, artist_mbid, image_url, local_image_path in rows
    }


def _require_user(session: Session, user_slug: str) -> User:
    user = session.scalars(select(User).where(User.slug == user_slug)).first()
    if user is None:
        raise KeyError(f"User not found: {user_slug}")
    return user


def _coverage(session: Session, user_id: int) -> dict:
    library_album_count = session.scalar(
        select(func.count(UserAlbum.id)).where(UserAlbum.user_id == user_id)
    ) or 0
    albums_with_facts = session.scalar(
        select(func.count(func.distinct(AlbumCreditFact.album_id)))
        .join(UserAlbum, UserAlbum.album_id == AlbumCreditFact.album_id)
        .where(UserAlbum.user_id == user_id)
    ) or 0
    fact_count = session.scalar(
        select(func.count(AlbumCreditFact.id))
        .join(UserAlbum, UserAlbum.album_id == AlbumCreditFact.album_id)
        .where(UserAlbum.user_id == user_id)
    ) or 0
    return {
        "library_album_count": library_album_count,
        "albums_with_facts": albums_with_facts,
        "projected_fact_count": fact_count,
        "coverage_ratio": albums_with_facts / library_album_count if library_album_count else 0,
    }


def _user_fact_rows(session: Session, user_id: int) -> list[dict]:
    rows = session.execute(
        select(
            AlbumCreditFact,
            Album.album_key,
            Album.artist,
            Album.name,
            Album.artist_mbid,
            Album.image_url,
            Album.local_image_path,
        )
        .join(Album, Album.id == AlbumCreditFact.album_id)
        .join(UserAlbum, UserAlbum.album_id == Album.id)
        .where(UserAlbum.user_id == user_id)
        .order_by(AlbumCreditFact.person_name, Album.artist, Album.name)
    ).all()
    return [
        {
            "fact": fact,
            "album_key": album_key,
            "artist": artist,
            "name": name,
            "artist_mbid": artist_mbid,
            "image_url": _display_image_url(image_url, local_image_path),
            "person_key": fact.person_key,
        }
        for fact, album_key, artist, name, artist_mbid, image_url, local_image_path in rows
    ]


def _eligible_recurring_contributors(session: Session, user_id: int) -> list[ContributorSummary]:
    contributors = _aggregate_contributors(_user_fact_rows(session, user_id), exclude_default_noise=True)
    ranked = [
        contributor
        for contributor in contributors.values()
        if len(contributor.album_ids) >= MIN_ALBUMS_FOR_RECURRING
        and len(contributor.artist_keys) >= MIN_PRIMARY_ARTISTS_FOR_RECURRING
    ]
    ranked.sort(key=_contributor_sort_key)
    return ranked


def _search_terms(query: str) -> list[str]:
    return [_normalize(term) for term in query.split() if _normalize(term)]


def _contributor_matches_search(contributor: ContributorSummary, terms: list[str]) -> bool:
    if not terms:
        return True
    searchable = " ".join(
        [contributor.person_name, *contributor.role_buckets.keys()]
    )
    normalized = _normalize(searchable)
    return all(term in normalized for term in terms)


def _aggregate_contributors(rows: list[dict], *, exclude_default_noise: bool) -> dict[str, ContributorSummary]:
    contributors: dict[str, ContributorSummary] = {}
    for row in rows:
        fact: AlbumCreditFact = row["fact"]
        flags = set(fact.quality_flags_json or [])
        if exclude_default_noise and _is_default_excluded(fact, flags):
            continue

        contributor = contributors.setdefault(
            fact.person_key,
            ContributorSummary(
                person_key=fact.person_key,
                person_name=fact.person_name,
                person_mbid=fact.person_mbid,
            ),
        )
        contributor.album_ids.add(fact.album_id)
        contributor.artist_keys.add(_artist_key(row["artist"], row["artist_mbid"]))
        contributor.role_buckets[fact.role_bucket] += 1
        contributor.raw_roles[fact.raw_role] += 1
        contributor.quality_flags.update(flags)
        contributor.identity_resolution.add(fact.identity_resolution)
        contributor.ingestion_versions.add(fact.ingestion_version)

        album = contributor.albums.setdefault(
            fact.album_id,
            AlbumFactSummary(
                album_id=fact.album_id,
                album_key=row["album_key"],
                artist=row["artist"],
                name=row["name"],
                artist_mbid=row["artist_mbid"],
                image_url=row["image_url"],
            ),
        )
        album.role_buckets[fact.role_bucket] += 1
        album.raw_roles[fact.raw_role] += 1
        album.quality_flags.update(flags)
        album.identity_resolution.add(fact.identity_resolution)
        album.ingestion_versions.add(fact.ingestion_version)

    return contributors


def _build_album_pairs(rows: list[dict]) -> list[AlbumCreditPairSummary]:
    grouped: dict[tuple[str, str], dict[int, AlbumPairFactSummary]] = {}
    contributor_names: dict[str, tuple[str, str | None]] = {}
    for row in rows:
        fact: AlbumCreditFact = row["fact"]
        flags = set(fact.quality_flags_json or [])
        if _is_default_excluded(fact, flags):
            continue
        if fact.role_bucket not in ALBUM_PAIR_ROLE_BUCKETS:
            continue
        contributor_names[fact.person_key] = (fact.person_name, fact.person_mbid)
        role_group = grouped.setdefault((fact.person_key, fact.role_bucket), {})
        album_summary = role_group.setdefault(
            fact.album_id,
            AlbumPairFactSummary(
                album=AlbumFactSummary(
                    album_id=fact.album_id,
                    album_key=row["album_key"],
                    artist=row["artist"],
                    name=row["name"],
                    artist_mbid=row["artist_mbid"],
                    image_url=row["image_url"],
                ),
            ),
        )
        album_summary.track_count += int(fact.track_count or 0)
        album_summary.role_buckets[fact.role_bucket] += 1
        album_summary.raw_roles[fact.raw_role] += 1
        album_summary.quality_flags.update(flags)
        album_summary.identity_resolution.add(fact.identity_resolution)
        album_summary.ingestion_versions.add(fact.ingestion_version)

    pairs: list[AlbumCreditPairSummary] = []
    seen_pair_keys: set[str] = set()
    for (person_key, role_bucket), albums_by_id in grouped.items():
        if len(albums_by_id) < 2:
            continue
        person_name, person_mbid = contributor_names[person_key]
        for album_a, album_b in combinations(
            sorted(albums_by_id.values(), key=lambda item: item.album.album_id),
            2,
        ):
            if _is_duplicate_album_pair(album_a.album, album_b.album):
                continue
            pair = AlbumCreditPairSummary(
                album_a=album_a,
                album_b=album_b,
                person_key=person_key,
                person_name=person_name,
                person_mbid=person_mbid,
                role_bucket=role_bucket,
                raw_roles=album_a.raw_roles + album_b.raw_roles,
                quality_flags=album_a.quality_flags | album_b.quality_flags,
                identity_resolution=album_a.identity_resolution | album_b.identity_resolution,
                ingestion_versions=album_a.ingestion_versions | album_b.ingestion_versions,
            )
            pair_key = _album_pair_key(pair)
            if pair_key in seen_pair_keys:
                continue
            seen_pair_keys.add(pair_key)
            pairs.append(pair)
    return pairs


def _album_summaries_from_rows(rows: list[dict]) -> dict[int, AlbumFactSummary]:
    albums: dict[int, AlbumFactSummary] = {}
    for row in rows:
        fact: AlbumCreditFact = row["fact"]
        album = albums.setdefault(
            fact.album_id,
            AlbumFactSummary(
                album_id=fact.album_id,
                album_key=row["album_key"],
                artist=row["artist"],
                name=row["name"],
                artist_mbid=row["artist_mbid"],
                image_url=row["image_url"],
            ),
        )
        album.role_buckets[fact.role_bucket] += 1
        album.raw_roles[fact.raw_role] += 1
        album.quality_flags.update(fact.quality_flags_json or [])
        album.identity_resolution.add(fact.identity_resolution)
        album.ingestion_versions.add(fact.ingestion_version)
    return albums


def _direct_album_connection_contributors(
    rows: list[dict],
    album_a_id: int,
    album_b_id: int,
) -> list[ContributorSummary]:
    contributors = _aggregate_contributors(rows, exclude_default_noise=True)
    connected = []
    for contributor in contributors.values():
        if album_a_id not in contributor.albums or album_b_id not in contributor.albums:
            continue
        album_a = contributor.albums[album_a_id]
        album_b = contributor.albums[album_b_id]
        if not any(role in GRAPH_ROLE_BUCKETS for role in album_a.role_buckets):
            continue
        if not any(role in GRAPH_ROLE_BUCKETS for role in album_b.role_buckets):
            continue
        connected.append(contributor)

    connected.sort(
        key=lambda contributor: (
            -sum(
                count
                for album_id in (album_a_id, album_b_id)
                for role, count in contributor.albums[album_id].role_buckets.items()
                if role in GRAPH_ROLE_BUCKETS
            ),
            _role_rank(_primary_graph_role(contributor.albums[album_a_id].role_buckets)),
            contributor.person_name.casefold(),
            contributor.person_key,
        )
    )
    return connected


def _album_connection_paths(
    graph: CreditConnectionGraph,
    album_a_id: int,
    album_b_id: int,
    *,
    deadline: float,
) -> AlbumConnectionPathSearch:
    return _search_album_connection_paths(
        graph,
        album_a_id,
        album_b_id,
        deadline=deadline,
    )


def _prepare_album_connection_graph(rows: list[dict]) -> CreditConnectionGraph:
    contributors = _reliable_graph_contributors(rows)
    contributors_by_album: dict[int, list[ContributorSummary]] = {}
    for contributor in contributors.values():
        for album_id, album in contributor.albums.items():
            if any(role in GRAPH_ROLE_BUCKETS for role in album.role_buckets):
                contributors_by_album.setdefault(album_id, []).append(contributor)

    return CreditConnectionGraph(
        contributors_by_album={
            album_id: tuple(album_contributors)
            for album_id, album_contributors in contributors_by_album.items()
        }
    )


def _search_album_connection_paths(
    graph: CreditConnectionGraph,
    album_a_id: int,
    album_b_id: int,
    *,
    deadline: float,
) -> AlbumConnectionPathSearch:
    contributors_by_album = graph.contributors_by_album

    paths: list[AlbumConnectionPath] = []
    seen_paths: set[tuple[tuple[int, ...], tuple[str, ...]]] = set()
    queue = deque([(album_a_id, [], frozenset({album_a_id}), frozenset())])
    seen_states = {(album_a_id, frozenset({album_a_id}), frozenset())}
    states_examined = 0
    edges_examined = 0
    max_queue_size = 1
    expansion_limited = False

    def result(*, limited: bool = False, reason: str | None = None):
        return AlbumConnectionPathSearch(
            paths=sorted(paths, key=_album_connection_path_sort_key),
            limited=limited,
            limited_reason=reason,
            states_examined=states_examined,
            edges_examined=edges_examined,
            max_queue_size=max_queue_size,
        )

    while queue:
        if time.monotonic() >= deadline:
            return result(limited=True, reason="time_limit")

        if states_examined >= MAX_ALBUM_CONNECTION_SEARCH_STATES:
            return result(limited=True, reason="state_limit")

        current_album_id, steps, used_albums, used_contributors = queue.popleft()
        states_examined += 1
        if len(steps) >= MAX_ALBUM_CONNECTION_CONTRIBUTOR_HOPS:
            continue

        for contributor in _rank_album_path_contributors(
            contributors_by_album.get(current_album_id, [])
        ):
            if time.monotonic() >= deadline:
                return result(limited=True, reason="time_limit")
            if contributor.person_key in used_contributors:
                continue
            ranked_album_ids = _rank_contributor_path_albums(contributor)
            if len(ranked_album_ids) > MAX_ALBUM_CONNECTION_ALBUMS_PER_CONTRIBUTOR:
                expansion_limited = True
                ranked_album_ids = ranked_album_ids[:MAX_ALBUM_CONNECTION_ALBUMS_PER_CONTRIBUTOR]
            for next_album_id in ranked_album_ids:
                if time.monotonic() >= deadline:
                    return result(limited=True, reason="time_limit")
                if edges_examined >= MAX_ALBUM_CONNECTION_SEARCH_EDGES:
                    return result(limited=True, reason="edge_limit")
                edges_examined += 1
                if next_album_id == current_album_id:
                    continue
                if next_album_id in used_albums and next_album_id != album_b_id:
                    continue
                next_steps = [
                    *steps,
                    AlbumConnectionStep(
                        contributor=contributor,
                        from_album_id=current_album_id,
                        to_album_id=next_album_id,
                        role_bucket=_connection_step_role(
                            contributor,
                            current_album_id,
                            next_album_id,
                        ),
                    ),
                ]
                if next_album_id == album_b_id:
                    path = AlbumConnectionPath(steps=next_steps)
                    path_key = (tuple(path.album_ids), tuple(path.contributor_keys))
                    if path_key not in seen_paths:
                        seen_paths.add(path_key)
                        paths.append(path)
                    if len(paths) >= MAX_ALBUM_CONNECTION_PATHS:
                        return result(limited=True, reason="result_limit")
                    continue
                if len(next_steps) < MAX_ALBUM_CONNECTION_CONTRIBUTOR_HOPS:
                    next_used_albums = used_albums | {next_album_id}
                    next_used_contributors = used_contributors | {contributor.person_key}
                    state = (next_album_id, next_used_albums, next_used_contributors)
                    if state in seen_states:
                        continue
                    if len(queue) >= MAX_ALBUM_CONNECTION_SEARCH_QUEUE_SIZE:
                        return result(limited=True, reason="queue_limit")
                    seen_states.add(state)
                    queue.append((next_album_id, next_steps, next_used_albums, next_used_contributors))
                    max_queue_size = max(max_queue_size, len(queue))

    return result(
        limited=expansion_limited,
        reason="expansion_limit" if expansion_limited else None,
    )


def _rank_album_path_contributors(
    contributors: list[ContributorSummary],
) -> list[ContributorSummary]:
    return sorted(
        contributors,
        key=lambda contributor: (
            _role_rank(_primary_graph_role(contributor.role_buckets)),
            -sum(contributor.role_buckets.values()),
            contributor.person_name.casefold(),
            contributor.person_key,
        ),
    )


def _rank_contributor_path_albums(contributor: ContributorSummary) -> list[int]:
    return [
        album.album_id
        for album in sorted(
            contributor.albums.values(),
            key=lambda album: (
                _role_rank(_primary_graph_role(album.role_buckets)),
                -sum(album.role_buckets.values()),
                album.artist.casefold(),
                album.name.casefold(),
                album.album_id,
            ),
        )
    ]


def _reliable_graph_contributors(rows: list[dict]) -> dict[str, ContributorSummary]:
    filtered_rows = []
    for row in rows:
        fact: AlbumCreditFact = row["fact"]
        flags = set(fact.quality_flags_json or [])
        if _is_default_excluded(fact, flags):
            continue
        if fact.role_bucket not in GRAPH_ROLE_BUCKETS:
            continue
        filtered_rows.append(row)
    return _aggregate_contributors(filtered_rows, exclude_default_noise=False)


def _connection_step_role(
    contributor: ContributorSummary,
    from_album_id: int,
    to_album_id: int,
) -> str:
    combined = contributor.albums[from_album_id].role_buckets + contributor.albums[to_album_id].role_buckets
    return _primary_graph_role(combined)


def _album_connection_path_sort_key(path: AlbumConnectionPath):
    evidence = sum(
        sum(
            count
            for role, count in step.contributor.albums[album_id].role_buckets.items()
            if role in GRAPH_ROLE_BUCKETS
        )
        for step in path.steps
        for album_id in (step.from_album_id, step.to_album_id)
    )
    identity_penalty = sum(
        0 if "mbid" in step.contributor.identity_resolution else 1
        for step in path.steps
    )
    role_rank = min((_role_rank(step.role_bucket) for step in path.steps), default=99)
    return (
        path.hop_count,
        identity_penalty,
        -evidence,
        role_rank,
        tuple(step.contributor.person_name.casefold() for step in path.steps),
        tuple(path.album_ids),
    )


def _album_connection_graph_payload(
    contributors: list[ContributorSummary],
    album_a_id: int,
    album_b_id: int,
    album_summaries: dict[int, AlbumFactSummary],
    *,
    best_path: AlbumConnectionPath | None = None,
) -> tuple[list[dict], list[dict]]:
    path_contributors = [step.contributor for step in best_path.steps] if best_path else []
    path_album_ids = set(best_path.album_ids) if best_path else set()
    contributor_list = _dedupe_contributors([*path_contributors, *contributors])
    album_nodes: dict[int, dict] = {
        album_id: {
            "id": _graph_album_id(album.album_id),
            "type": "album",
            "label": album.name,
            "album_id": album.album_id,
            "album_key": album.album_key,
            "artist": album.artist,
            "image_url": album.image_url,
            "role_buckets": Counter(album.role_buckets),
            "quality_flags": set(album.quality_flags),
            "identity_resolution": set(album.identity_resolution),
            "ingestion_versions": set(album.ingestion_versions),
            "connected_contributor_count": 0,
        }
        for album_id, album in album_summaries.items()
        if album_id in ({album_a_id, album_b_id} | path_album_ids)
    }
    contributor_nodes = []
    edges = []

    for contributor in contributor_list:
        contributor_id = _graph_contributor_id(contributor.person_key)
        contributor_nodes.append(
            {
                "id": contributor_id,
                "type": "contributor",
                "label": contributor.person_name,
                "person_key": contributor.person_key,
                "person_mbid": contributor.person_mbid,
                "connected_album_count": len(contributor.album_ids),
                "distinct_primary_artist_count": len(contributor.artist_keys),
                "role_buckets": dict(contributor.role_buckets.most_common()),
                "quality_flags": sorted(contributor.quality_flags),
                "identity_resolution": sorted(contributor.identity_resolution),
                "ingestion_versions": sorted(contributor.ingestion_versions),
            }
        )
        for album_id in sorted(set(contributor.albums) & set(album_nodes)):
            album = contributor.albums[album_id]
            album_node = album_nodes[album_id]
            album_node["role_buckets"].update(album.role_buckets)
            album_node["quality_flags"].update(album.quality_flags)
            album_node["identity_resolution"].update(album.identity_resolution)
            album_node["ingestion_versions"].update(album.ingestion_versions)
            role_bucket = _primary_graph_role(album.role_buckets)
            edges.append(
                {
                    "id": f"{contributor_id}->{album_node['id']}:{role_bucket}",
                    "source": contributor_id,
                    "target": album_node["id"],
                    "role_bucket": role_bucket,
                    "raw_roles": dict(album.raw_roles.most_common(10)),
                    "quality_flags": sorted(album.quality_flags),
                    "identity_resolution": sorted(album.identity_resolution),
                    "ingestion_versions": sorted(album.ingestion_versions),
                }
            )

    for album_node in album_nodes.values():
        album_node["connected_contributor_count"] = len(
            [
                contributor
                for contributor in contributor_list
                if album_node["album_id"] in contributor.albums
            ]
        )
        album_node["role_buckets"] = dict(album_node["role_buckets"].most_common())
        album_node["quality_flags"] = sorted(album_node["quality_flags"])
        album_node["identity_resolution"] = sorted(album_node["identity_resolution"])
        album_node["ingestion_versions"] = sorted(album_node["ingestion_versions"])

    return [*contributor_nodes, *album_nodes.values()], edges


def _dedupe_contributors(contributors: list[ContributorSummary]) -> list[ContributorSummary]:
    deduped = []
    seen = set()
    for contributor in contributors:
        if contributor.person_key in seen:
            continue
        seen.add(contributor.person_key)
        deduped.append(contributor)
    return deduped


def _is_default_excluded(fact: AlbumCreditFact, flags: set[str]) -> bool:
    if fact.role_bucket in DEFAULT_EXCLUDED_ROLE_BUCKETS:
        return True
    if _normalize(fact.person_name) in DEFAULT_EXCLUDED_NORMALIZED_NAMES:
        return True
    return bool(flags & DEFAULT_EXCLUDED_FLAGS)


def _is_duplicate_album_pair(left: AlbumFactSummary, right: AlbumFactSummary) -> bool:
    if left.album_id == right.album_id:
        return True
    if left.album_key and right.album_key and left.album_key == right.album_key:
        return True
    return (
        _normalize(left.artist) == _normalize(right.artist)
        and _normalize(left.name) == _normalize(right.name)
    )


def _contributor_sort_key(contributor: ContributorSummary):
    return (
        -len(contributor.album_ids),
        -len(contributor.artist_keys),
        contributor.person_name.casefold(),
        contributor.person_key,
    )


def _album_pair_sort_key(pair: AlbumCreditPairSummary):
    return (
        not pair.cross_primary_artist,
        -pair.evidence_track_count,
        _role_rank(pair.role_bucket),
        pair.person_name.casefold(),
        pair.album_a.album.artist.casefold(),
        pair.album_a.album.name.casefold(),
        pair.album_b.album.artist.casefold(),
        pair.album_b.album.name.casefold(),
        pair.person_key,
    )


def _role_rank(role_bucket: str) -> int:
    order = {
        "producer": 0,
        "writer_composer": 1,
        "mixing_mastering": 2,
        "engineering": 3,
        "performer": 4,
    }
    return order.get(role_bucket, 99)


def _contributor_payload(contributor: ContributorSummary) -> dict:
    albums = _rank_albums(contributor)
    return {
        "person_key": contributor.person_key,
        "person_name": contributor.person_name,
        "person_mbid": contributor.person_mbid,
        "identity_resolution": sorted(contributor.identity_resolution),
        "ingestion_versions": sorted(contributor.ingestion_versions),
        "connected_album_count": len(contributor.album_ids),
        "distinct_primary_artist_count": len(contributor.artist_keys),
        "role_buckets": dict(contributor.role_buckets.most_common()),
        "raw_roles": dict(contributor.raw_roles.most_common(10)),
        "quality_flags": sorted(contributor.quality_flags),
        "representative_albums": [_album_payload(album) for album in albums[:5]],
        "representative_artists": _representative_artists(albums),
    }


def _graph_payload(
    contributors: list[ContributorSummary],
    album_limit_per_contributor: int,
    album_limit: int,
) -> tuple[list[dict], list[dict]]:
    nodes: list[dict] = []
    edges: list[dict] = []
    album_nodes: dict[int, dict] = {}
    album_connected_people: dict[int, set[str]] = {}

    for contributor in contributors:
        contributor_id = _graph_contributor_id(contributor.person_key)
        nodes.append(
            {
                "id": contributor_id,
                "type": "contributor",
                "label": contributor.person_name,
                "person_key": contributor.person_key,
                "person_mbid": contributor.person_mbid,
                "connected_album_count": len(contributor.album_ids),
                "distinct_primary_artist_count": len(contributor.artist_keys),
                "role_buckets": dict(contributor.role_buckets.most_common()),
                "quality_flags": sorted(contributor.quality_flags),
                "identity_resolution": sorted(contributor.identity_resolution),
                "ingestion_versions": sorted(contributor.ingestion_versions),
            }
        )

        graph_albums = [
            album
            for album in contributor.albums.values()
            if any(role in GRAPH_ROLE_BUCKETS for role in album.role_buckets)
        ]
        graph_albums.sort(key=_graph_album_sort_key)
        for album in graph_albums[:album_limit_per_contributor]:
            if album.album_id not in album_nodes and len(album_nodes) >= album_limit:
                continue
            album_node = album_nodes.setdefault(
                album.album_id,
                {
                    "id": _graph_album_id(album.album_id),
                    "type": "album",
                    "label": album.name,
                    "album_id": album.album_id,
                    "album_key": album.album_key,
                    "artist": album.artist,
                    "image_url": album.image_url,
                    "role_buckets": Counter(),
                    "quality_flags": set(),
                    "identity_resolution": set(),
                    "ingestion_versions": set(),
                    "connected_contributor_count": 0,
                },
            )
            album_connected_people.setdefault(album.album_id, set()).add(contributor.person_key)
            album_node["role_buckets"].update(album.role_buckets)
            album_node["quality_flags"].update(album.quality_flags)
            album_node["identity_resolution"].update(album.identity_resolution)
            album_node["ingestion_versions"].update(album.ingestion_versions)
            role_bucket = _primary_graph_role(album.role_buckets)
            edges.append(
                {
                    "id": f"{contributor_id}->{album_node['id']}:{role_bucket}",
                    "source": contributor_id,
                    "target": album_node["id"],
                    "role_bucket": role_bucket,
                    "raw_roles": dict(album.raw_roles.most_common(10)),
                    "quality_flags": sorted(album.quality_flags),
                    "identity_resolution": sorted(album.identity_resolution),
                    "ingestion_versions": sorted(album.ingestion_versions),
                }
            )

    for album_id, album_node in album_nodes.items():
        album_node["connected_contributor_count"] = len(album_connected_people.get(album_id, set()))
        album_node["role_buckets"] = dict(album_node["role_buckets"].most_common())
        album_node["quality_flags"] = sorted(album_node["quality_flags"])
        album_node["identity_resolution"] = sorted(album_node["identity_resolution"])
        album_node["ingestion_versions"] = sorted(album_node["ingestion_versions"])

    return [*nodes, *album_nodes.values()], edges


def _album_pair_payload(pair: AlbumCreditPairSummary) -> dict:
    return {
        "pair_key": _album_pair_key(pair),
        "album_a": _album_payload(pair.album_a.album),
        "album_b": _album_payload(pair.album_b.album),
        "contributor": {
            "person_key": pair.person_key,
            "person_name": pair.person_name,
            "person_mbid": pair.person_mbid,
            "role_bucket": pair.role_bucket,
            "raw_roles": dict(pair.raw_roles.most_common(10)),
            "quality_flags": sorted(pair.quality_flags),
            "identity_resolution": sorted(pair.identity_resolution),
            "ingestion_versions": sorted(pair.ingestion_versions),
        },
        "cross_primary_artist": pair.cross_primary_artist,
        "evidence_track_count": pair.evidence_track_count,
    }


def _album_connection_contributor_payload(
    contributor: ContributorSummary,
    album_a_id: int,
    album_b_id: int,
) -> dict:
    album_a = contributor.albums[album_a_id]
    album_b = contributor.albums[album_b_id]
    return {
        "person_key": contributor.person_key,
        "person_name": contributor.person_name,
        "person_mbid": contributor.person_mbid,
        "role_buckets": dict(contributor.role_buckets.most_common()),
        "album_a_role_buckets": dict(album_a.role_buckets.most_common()),
        "album_b_role_buckets": dict(album_b.role_buckets.most_common()),
        "raw_roles": dict((album_a.raw_roles + album_b.raw_roles).most_common(10)),
        "quality_flags": sorted(album_a.quality_flags | album_b.quality_flags),
        "identity_resolution": sorted(album_a.identity_resolution | album_b.identity_resolution),
        "ingestion_versions": sorted(album_a.ingestion_versions | album_b.ingestion_versions),
    }


def _album_connection_path_payload(
    path: AlbumConnectionPath,
    album_summaries: dict[int, AlbumFactSummary],
) -> dict:
    steps = []
    for index, step in enumerate(path.steps, start=1):
        from_album = album_summaries[step.from_album_id]
        to_album = album_summaries[step.to_album_id]
        from_roles = step.contributor.albums[step.from_album_id].role_buckets
        to_roles = step.contributor.albums[step.to_album_id].role_buckets
        role_bucket = step.role_bucket
        steps.append(
            {
                "step_number": index,
                "from_album": _album_payload(from_album),
                "to_album": _album_payload(to_album),
                "contributor": {
                    "person_key": step.contributor.person_key,
                    "person_name": step.contributor.person_name,
                    "person_mbid": step.contributor.person_mbid,
                    "role_bucket": role_bucket,
                    "role_buckets": dict(step.contributor.role_buckets.most_common()),
                    "raw_roles": dict(
                        (
                            step.contributor.albums[step.from_album_id].raw_roles
                            + step.contributor.albums[step.to_album_id].raw_roles
                        ).most_common(10)
                    ),
                    "quality_flags": sorted(
                        step.contributor.albums[step.from_album_id].quality_flags
                        | step.contributor.albums[step.to_album_id].quality_flags
                    ),
                    "identity_resolution": sorted(step.contributor.identity_resolution),
                    "ingestion_versions": sorted(step.contributor.ingestion_versions),
                },
                "from_album_role_buckets": dict(from_roles.most_common()),
                "to_album_role_buckets": dict(to_roles.most_common()),
                "explanation": (
                    f"{step.contributor.person_name} connects {from_album.name} "
                    f"to {to_album.name} through {_role_label(role_bucket)} credits."
                ),
            }
        )

    intermediate_names = [
        album_summaries[album_id].name
        for album_id in path.album_ids[1:-1]
        if album_id in album_summaries
    ]
    explanation = (
        "This is the shortest credit path found after excluding default identity and primary-artist noise."
        if path.hop_count == 1
        else (
            f"This is a {path.hop_count}-step credit path through "
            f"{_join_names(intermediate_names)}, found after excluding default identity and primary-artist noise."
        )
    )
    return {
        "path_id": "path:" + "->".join(
            [
                _graph_album_id(path.album_ids[0]),
                *[
                    part
                    for step in path.steps
                    for part in (_graph_contributor_id(step.contributor.person_key), _graph_album_id(step.to_album_id))
                ],
            ]
        ),
        "hop_count": path.hop_count,
        "album_ids": path.album_ids,
        "contributor_keys": path.contributor_keys,
        "steps": steps,
        "explanation": explanation,
    }


def _role_label(role_bucket: str) -> str:
    return role_bucket.replace("_", " ")


def _join_names(names: list[str]) -> str:
    if not names:
        return "intermediate albums"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _album_pair_key(pair: AlbumCreditPairSummary) -> str:
    left_id, right_id = sorted([pair.album_a.album.album_id, pair.album_b.album.album_id])
    return f"{left_id}:{right_id}:{pair.person_key}:{pair.role_bucket}"


def _album_payload(album: AlbumFactSummary) -> dict:
    return {
        "album_id": album.album_id,
        "album_key": album.album_key,
        "artist": album.artist,
        "name": album.name,
        "role_buckets": dict(album.role_buckets.most_common()),
        "raw_roles": dict(album.raw_roles.most_common(10)),
        "quality_flags": sorted(album.quality_flags),
        "identity_resolution": sorted(album.identity_resolution),
        "ingestion_versions": sorted(album.ingestion_versions),
    }


def _graph_album_sort_key(album: AlbumFactSummary):
    graph_role_count = sum(
        count for role, count in album.role_buckets.items() if role in GRAPH_ROLE_BUCKETS
    )
    return (
        -graph_role_count,
        album.artist.casefold(),
        album.name.casefold(),
        album.album_id,
    )


def _primary_graph_role(role_buckets: Counter[str]) -> str:
    graph_roles = {
        role: count for role, count in role_buckets.items() if role in GRAPH_ROLE_BUCKETS
    }
    if not graph_roles:
        return "other"
    return sorted(graph_roles.items(), key=lambda item: (-item[1], _role_rank(item[0]), item[0]))[0][0]


def _graph_contributor_id(person_key: str) -> str:
    return f"contributor:{person_key}"


def _graph_album_id(album_id: int) -> str:
    return f"album:{album_id}"


def _rank_albums(contributor: ContributorSummary) -> list[AlbumFactSummary]:
    return sorted(
        contributor.albums.values(),
        key=lambda album: (
            album.artist.casefold(),
            album.name.casefold(),
            album.album_id,
        ),
    )


def _representative_artists(albums: list[AlbumFactSummary]) -> list[str]:
    seen = set()
    artists = []
    for album in albums:
        key = _normalize(album.artist)
        if key in seen:
            continue
        seen.add(key)
        artists.append(album.artist)
        if len(artists) >= 5:
            break
    return artists


def _artist_key(artist: str, artist_mbid: str | None) -> str:
    if artist_mbid:
        return f"mbid:{artist_mbid}"
    return f"name:{_normalize(artist)}"


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.casefold()).strip()


def _display_image_url(image_url: str | None, local_image_path: str | None) -> str | None:
    if local_image_path:
        filename = local_image_path.removeprefix("artwork/").lstrip("/")
        return f"{ARTWORK_URL_PREFIX}{filename}"
    return image_url


def _insufficient_data_reason(coverage: dict, results: list[dict]) -> str | None:
    if coverage["library_album_count"] == 0:
        return "empty_library"
    if coverage["albums_with_facts"] == 0:
        return "no_projected_credit_facts"
    if coverage["albums_with_facts"] < MIN_ALBUMS_WITH_FACTS_FOR_CONFIDENT_RESULTS:
        return "low_credit_fact_coverage"
    if not results:
        return "no_recurring_contributors_after_filters"
    return None
