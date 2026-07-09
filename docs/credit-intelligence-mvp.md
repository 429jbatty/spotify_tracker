# Albumary Credit Intelligence MVP

## 1. Purpose

Albumary should help users understand the people and creative relationships behind the albums they listen to.

The MVP should turn album-credit data into personalized, explainable insights such as:

- Which producers, musicians, writers, mixers, and engineers recur most often in a user’s library
- Which people connect otherwise separate artists or albums
- How albums, contributors, artists, and roles connect in an interactive map
- Which hidden creative threads exist across the user’s listening history

The feature should feel like a music-discovery product with an interactive
relationship map, not a static analytics report or graph-analysis tool.

The central product promise is:

> Discover the people behind your music and the hidden connections across your library.

---

## 2. Product Goal

The MVP should prove that personalized credit relationships are:

1. Understandable without knowledge of graph theory
2. Interesting enough to encourage further exploration
3. Distinct from ordinary listening-stat features
4. Reliable enough that users trust the surfaced connections
5. Useful as a focused interactive graph/map without requiring a graph database
   or an uncontrolled whole-library visualization

The MVP is successful if users can quickly answer:

- Who keeps appearing in the music I listen to?
- Which behind-the-scenes people shape my listening?
- Which albums in my library are secretly connected?
- Where should I explore next?

---

## 3. Product Principles

### 3.1 Explain the result, not the algorithm

Graph algorithms may be used internally, but the interface should use plain music language.

Good:

> Nigel Godrich appears on 8 albums by 4 artists in your library.

Avoid:

> Nigel Godrich has a degree centrality score of 0.18.

### 3.2 Metadata relationships come first

Insights should be based on the user’s own library and projected album-credit
metadata.

The system should prefer connections involving:

- Albums in the user's library
- Contributors who recur across the user’s library
- Connections between different artists, roles, eras, genres, or listening
  clusters when that metadata is available

### 3.3 Quality is more important than completeness

The system should prefer a smaller number of strong, understandable results over a comprehensive but noisy credit graph.

It is acceptable to omit weak or uncertain connections.

### 3.4 The graph is the interaction layer, not the explanation

The underlying data can be modeled as a bipartite graph:

```text
Album ↔ Person
```

The primary user experience should be a focused, explainable interactive map:

- Contributor nodes
- Album nodes
- Role-labeled edges
- Side-panel details
- Highlighting and focused exploration

The MVP should not render a giant uncontrolled whole-library graph. It should
render a curated, responsive map that keeps explanations visible and avoids
graph-theory language.

### 3.5 Every insight should be traceable

Every user-facing statement should be supportable with visible facts such as:

- Number of connected albums
- Number of connected primary artists
- Contributor role
- Relevant albums
- Role buckets
- Quality flags when relevant
- Connected albums and contributors

Avoid opaque composite scores in the interface.

---

## 4. Target User Experience

The MVP should contain three connected experiences:

1. Credit Profile
2. Interactive Connections Map
3. Contributor and Album Detail

These experiences should link to one another inside a graph-led discovery
workspace. The graph should be the main environment, while the page gives users
clear guided ways to enter and continue exploring it.

Example flow:

1. A user sees that a producer is a hidden connector in their library.
2. The user selects that producer in the map.
3. Connected albums highlight, with role labels explaining the relationships.
4. The side panel explains why the contributor matters and suggests a next
   album, person, or path to explore.
5. The user opens an album or contributor detail panel for structured facts
   when they want more detail.

---

# 5. Experience One: Credit Profile

## 5.1 Purpose

The Credit Profile is the main landing experience for the feature.

It should summarize the contributors and relationships hidden inside the user’s listening history.

Recommended page title:

# Behind Your Music

Recommended subtitle:

> The producers, musicians, writers, and engineers connecting your library.

The route and navigation label may be adapted to existing Albumary conventions.

Recommended navigation label:

**Connections**

---

## 5.2 Summary Metrics

The page may include a compact summary such as:

- Credited people in the user’s library
- Recurring contributors
- Distinct artists connected through credits
- Strongest current connector

These metrics should support the page rather than dominate it. Operational
coverage, ingestion, and quality metadata should stay out of the normal user
path unless it directly explains a selected relationship.

Avoid presenting too many abstract metrics.

---

## 5.3 Primary Surface: Interactive Connections Map

### User question

> How do the albums and credited people in my library connect?

### Definition

Render a focused interactive node/branch map using the user's library albums
and meaningful projected credit facts.

The initial relationship is:

```text
Album ↔ Contributor
```

Edges should carry role information such as producer, writer/composer,
performer, engineering, mixing, or mastering.

### Display requirements

The map should include:

- Album nodes
- Contributor nodes
- Role-labeled or role-colored connections
- A compact legend
- Hover or selected-node details
- Click behavior that highlights directly connected nodes
- Existing album detail handoff when selecting an album
- Visible labels for contributor nodes in focused views
- Clear visual states for selected nodes, path endpoints, intermediate albums,
  and intermediate contributors
- A state-specific heading, such as a contributor network, an album
  neighborhood, or a connection between two albums
- Suggested next explorations after a user selects a person, album, or path

### Product rules

- Engineering, mixing, and mastering are meaningful roles and should not be
  hidden by default.
- Do not use listen counts as the ranking or display basis.
- Start with a curated subset so the map is legible.
- Avoid graph-theory labels such as centrality, degree, or edge weight.
- Keep a structured list or side panel for accessibility and scannability.
- Entry controls should be mode-specific. Do not permanently show every
  possible starting control at once.
- The two-album connector should appear as a graph entry mode, not as a
  separate static report.
- Recurring contributor cards should act as alternate entrances back into the
  graph, not compete with the graph as the main surface.

---

## 5.4 Supporting Insight: Most Recurring Contributors

### User question

> Who keeps appearing in the albums I listen to?

### Definition

Rank people by the number of distinct albums in the user’s library on which they have meaningful credits.

### Display requirements

Each result should include:

- Person name
- Primary or most common role
- Number of connected albums
- Number of connected primary artists
- Representative albums
- Plain-language explanation

Example:

> **Nigel Godrich**  
> Producer on 8 albums by 4 artists in your library.

### Product rules

- Do not allow primary artists to overwhelm behind-the-scenes rankings.
- Prefer separate role groupings where useful.
- Count distinct underlying albums rather than duplicate editions.
- Require meaningful, sufficiently confident credits.

Suggested role groupings:

- Producers and writers
- Performers
- Mixing and engineering
- All behind-the-scenes contributors

---

## 5.5 Supporting Insight: Hidden Connectors

### User question

> Who connects otherwise separate parts of my taste?

### Definition

Identify contributors who connect albums by several distinct primary artists.

The initial implementation does not need to use full graph betweenness centrality.

A simpler connector model may use:

- Number of distinct primary artists connected
- Number of distinct albums connected
- Number of artist pairs created
- Credit strength

### Display requirements

Each result should include:

- Person name
- Relevant role or roles
- Number of albums connected
- Distinct artists connected
- Representative artists or albums
- Clear explanation

Example:

> **Adrian Belew**  
> Connects 7 albums across David Bowie, Talking Heads, King Crimson, and Nine Inch Nails.

### Product rules

- Prefer connections across at least three distinct primary artists.
- Exclude trivial same-artist relationships.
- Down-rank contributors whose connections come primarily from compilations, reissues, bonus tracks, or large ensembles.
- Do not expose a centrality score.

---

## 5.6 Deferred Insight: Static Album Connections

### User question

> Which albums in my library share an unexpected creative connection?

### Definition

Surface pairs of albums connected by one or more meaningful shared contributors.

The initial relationship is:

```text
Album → Person → Album
```

### Product decision

Static album-pair cards were tested in implementation Phase 6 and were not
compelling enough as a default page section. The backend relationship remains
useful, but the default UX should move this information into the interactive
map, hover/details, or future focused lookup rather than a standalone card list.

If this returns later, each result should include:

- Both albums
- Shared person
- Shared role or roles
- Short explanation
- Action to explore the connection

Example:

> *In Rainbows* and *Sea Change* are connected by producer Nigel Godrich.

### Product rules

Prefer album pairs where:

- The primary artists differ
- The credit is strong and understandable
- The relationship is not caused by duplicate editions
- The connection is not obvious solely because of the same band lineup

---

# 6. Experience Two: Contributor And Album Detail

## 6.1 Purpose

The detail experience gives users a clear destination after selecting a
contributor or album from the map or supporting list.

It should provide structured facts that complement the graph visualization.

---

## 6.2 Required content

### Header

Show:

- Person name
- Most common or most relevant role
- Number of connected albums
- Number of connected primary artists

### Summary

Generate a concise factual explanation.

Example:

> Nigel Godrich appears across 8 albums in your library, spanning Radiohead, Beck, Air, and R.E.M.

### Connected albums

Display albums connected to the person.

Each album should show:

- Artwork
- Album title
- Primary artist
- Release year
- Person’s role
- Whether the credit is album-wide or track-specific, when relevant

### Sorting

Optional sorts:

- Most recent
- Release date
- Role

### Direct connections

Where useful, show notable album pairs connected by the person.

Example:

> Also connects *In Rainbows* and *Sea Change* as producer.

---

# 7. Graph-Integrated Album Connector

## 7.1 Purpose

Allow a user to select two albums from their library and see how they are
connected through credited people.

This should behave as an entry mode inside the interactive map, not as a
separate lower-page report or static card section.

---

## 7.2 Interface

Provide two searchable album selectors:

```text
Connect [Album A] to [Album B]
```

Primary action:

**Find Connection**

For the MVP, both albums should come from the user’s Albumary library.

The selectors should only appear when the user activates the connect-two-albums
mode. Large libraries require searchable inputs with small result lists; native
dropdowns are not acceptable.

---

## 7.3 Direct connection result

The initial result type is:

```text
Album A → Person → Album B
```

Example:

```text
Kid A
Produced by
Nigel Godrich
Produced
Sea Change
```

Summary:

> Nigel Godrich produced both *Kid A* and *Sea Change*.

---

## 7.4 Multi-step connection result

After direct connections are reliable, support bounded multi-step paths:

```text
Album A → Person → Album C → Person → Album B
```

The path should remain short enough to understand.

Recommended maximum for the MVP:

- At most four contributor hops
- No unbounded whole-library traversal

Longer paths should be excluded rather than displayed as confusing chains. The
experience should favor surprising but readable connections over exhaustive path
enumeration.

---

## 7.5 Path selection rules

The mathematically shortest path should not automatically be selected if it relies on weak or low-confidence credits.

The preferred path should balance:

- Path length
- Credit confidence
- Role significance
- Album-level versus track-level scope
- Number of tracks involved
- Compilation or reissue noise
- Ease of explanation

Prefer paths involving:

- Producer
- Writer or composer
- Major performer
- Featured performer
- Mixer
- Recording engineer
- Mastering engineer

Down-rank or label paths involving:

- Low-confidence credits
- Generic assistance roles
- One-track bonus credits
- Large ensemble members with weak participation
- Compilation-only relationships
- Duplicate editions of the same album
- Unresolved person identities

`single_track_credit` and `low_track_share` links remain eligible for now. Treat
those flags as evidence labels for explanation and future ranking, not as hard
blockers.

The path system may use weighting internally, but the interface should not
display raw path scores. Do not add a user-facing selector for "shortest",
"strongest", or "alternative" paths until the basic path explanation and graph
legibility are refined.

---

## 7.6 Empty states

When no reliable path exists:

> No reliable credit path was found between these albums in your current library.

Do not force a weak result simply because a technical path exists.

When credit coverage is insufficient:

> Albumary does not yet have enough reliable credit data to connect these albums.

---

# 8. Credit Roles

## 8.1 Role preservation

Albumary should preserve:

- Raw source role
- Normalized role
- Broad role category

Do not discard original source detail during normalization.

---

## 8.2 Recommended role categories

The MVP should support categories similar to:

```text
primary_artist
producer
writer_composer
performer
featured_performer
mixing
recording_engineering
mastering
other_technical
other
```

Exact names may be adapted to the current application.

---

## 8.3 Role interpretation

Role importance is contextual.

Do not assume one universal ranking always applies across all music.

Examples:

- Producers may be especially meaningful in pop, rock, electronic, and hip-hop.
- Session performers may be especially meaningful in jazz, soul, and funk.
- Engineers and mixers may reveal strong recurring technical networks.
- Large ensemble credits may create noise.

Prefer comparing contributors within meaningful role groups instead of forcing every role into one universal leaderboard.

---

# 9. Credit Strength and Data Quality

## 9.1 Core requirement

The biggest product risk is not graph size. It is weak or misleading credit data.

The MVP must include a way to evaluate whether an album-person relationship is strong enough to use.

---

## 9.2 Suggested credit-strength inputs

A connection may consider:

- Source confidence
- Album-level versus track-level credit
- Number of tracks involved
- Proportion of album tracks involved
- Normalized role
- Primary versus supplemental credit
- Whether the album is a compilation
- Whether the release is a reissue, deluxe edition, or remaster
- Whether the contributor is part of a very large ensemble
- Whether the person identity is resolved

The exact implementation should be adapted to Albumary’s available data.

---

## 9.3 Quality rules

The system should exclude or down-rank:

- Unresolved contributors
- Duplicate person identities
- Duplicate album editions
- Compilation artifacts
- Reissue-only or archival relationships
- Bonus-track-only contributors
- Very low-confidence credits
- Generic roles with little explanatory value
- Large ensemble members when participation creates hundreds of weak links

The system should retain the raw data even when it excludes a relationship from insights.

---

# 10. Personalization

## 10.1 Listening weighting

Connections ranking should not use listening history in the current MVP. The
feature is about metadata relationships across albums, not replay frequency.

Potential future signals outside the current Connections MVP:

- Album listen count
- Completed listens
- Recent listening
- User rating or favorite status, if available
- Whether the album is in the user’s active library

If listening impact returns later, it should be a separate interpretable insight
type, not an input into the default credit graph ranking. The MVP should not
create a single opaque "importance score" that combines every signal.

Prefer separate interpretable measures:

- Library reach
- Listening impact, only in a separately approved future view
- Distinct artists connected
- Direct album relationships

---

## 10.2 Avoid domination by one album

If raw listen counts are approved for a future non-MVP view, one heavily
replayed album may dominate.

The implementation should use a reasonable normalization such as:

- Log scaling
- Capping
- Percentile normalization
- Time-window normalization

The exact formula should be documented and testable.

---

# 11. Insight Generation Rules

The MVP should use specific insight types rather than one generalized “interestingness score.”

Recommended insight types:

## 11.1 Recurring Contributor

A person appears on several distinct albums.

## 11.2 Listening Shaper

Deferred from the current MVP. If approved later, this would describe a person
associated with a large share of the user's listening without influencing the
default Connections graph ranking.

## 11.3 Hidden Connector

A person connects several distinct primary artists.

## 11.4 Shared Credit

Two albums share a meaningful contributor.

## 11.5 Hidden Role

A behind-the-scenes contributor has unusual reach in the user’s library.

Potential future insight types, not required for the MVP:

- Recent emergence
- Cross-decade bridge
- Cross-genre bridge
- Community or scene center
- External-catalog discovery

---

# 12. Sparse-Library Behavior

The feature should remain useful for users with small libraries or limited listening history.

The system should not require every user to have a dense graph.

For sparse users:

- Show direct shared-credit relationships
- Show contributor details for individual albums
- Highlight recurring people even if only two albums are involved
- Explain that more connections will appear as the library grows
- Avoid empty leaderboards with arbitrary low-quality results

Example empty state:

> Add more completed albums to reveal recurring producers, performers, and engineers across your library.

Do not classify users into taste personas or listening types.

---

# 13. MVP Scope

## 13.1 Required

The MVP must include:

### Credit Profile

- Most recurring contributors
- Interactive connections map
- Hidden connector/contextual contributor details

### Contributor and Album Detail

- Connected albums
- Roles
- Distinct artists
- Clear summary

### Interactive Map

- Album and contributor nodes
- Role-aware edges
- Highlighting for selected nodes
- Detail panel or existing album handoff
- Empty and insufficient-data states that explain missing credit coverage

### Data-quality support

- Person identity handling
- Role normalization
- Duplicate-edition handling
- Credit confidence or strength
- Track-level versus album-level awareness
- Filtering or visible labeling of weak relationships

---

## 13.2 Explicitly out of scope

Do not include these in the MVP unless later approved:

- Full freeform graph visualization
- Giant whole-library node graph
- Three-hop expansion controls
- PageRank
- Eigenvector centrality
- User-facing centrality scores
- Louvain or Leiden community detection
- Global external-catalog exploration
- Graph database adoption
- User-configurable role weights
- Large advanced-filter panels
- AI-generated narrative insights
- Listening-impact rankings
- Static album-pair card sections
- Standalone two-album finder outside the graph workspace
- Precomputed shortest paths between all album pairs
- User-facing path-score controls such as "shortest" versus "strongest"
- Genre-crossing scores
- Decade-crossing scores
- Social or sharing features
- Public contributor profiles
- Universal credit search outside the user’s library

---

# 14. Recommended Delivery Phases

The repository-specific implementation plan may adjust these phases, but the product sequence should remain broadly similar.

## Phase 1: Credit Data Audit

Validate:

- Credit coverage by album
- Role consistency
- Person identity quality
- Duplicate people
- Duplicate releases
- Track-level coverage
- Noisy albums
- Compilation and reissue behavior
- Preliminary rankings

This phase should produce inspectable internal output before public UI work begins.

## Phase 2: Recurring Contributors

Deliver:

- Role normalization required for recurrence
- Person-album aggregation
- Recurring-contributor API
- Credit Profile section
- Person Detail experience

## Phase 3: Remove Listening Impact From Connections

Deliver:

- Product rule that Connections is based on metadata relationships, not listen
  frequency
- Removal of listen-count ranking/display from the Connections feature
- Validation that contributor and album payloads do not expose listen-count
  fields

Status:

- Completed in the repository-specific implementation plan. Listening impact is
  not part of the current MVP.

## Phase 4: Direct Album Connections Data

Deliver:

- Direct shared-credit lookup
- Suppression of weak duplicate/noisy links
- Traceable album-person-album payloads

Status:

- Superseded for the default MVP surface. Static direct album connections were
  tested and should move behind the interactive map or a later focused lookup.

## Phase 5: Interactive Connections Map

Deliver:

- Focused album/contributor node map
- Role-colored or role-labeled edges
- Node selection and connected-node highlighting
- Contributor detail side panel
- Existing album detail handoff

## Phase 6: Bounded Multi-Step Paths

Deliver:

- Bounded album-to-album pathfinding inside the graph workspace
- At most four contributor hops
- Role-aware explanation
- Evidence labels for low-share or single-track links
- No-path states that do not invent weak connections

Status:

- Implemented in the repository-specific plan, with further explanation and
  layout refinement moved to the next implementation phase.

## Phase 7: Hidden Connectors

Deliver:

- Distinct-artist connector logic
- Hidden-connector cards
- Representative artists and albums
- Manual result validation

A larger freeform graph should be considered only after the focused map proves
useful.

---

# 15. Acceptance Criteria

The MVP is ready when all of the following are true:

1. A user can open the feature and see personalized credit insights.
2. The Credit Profile contains a focused interactive connections map plus
   supporting contributor information.
3. Every insight includes a factual explanation.
4. Every displayed contributor can be inspected in a detail experience.
5. Detail panels show the relevant albums and roles.
6. A user can select graph nodes and see directly connected albums or
   contributors.
7. Role information is visible for graph edges or selected-node details.
8. Weak, low-confidence, duplicate, and noisy relationships are either
   suppressed where appropriate or clearly labeled when they remain eligible.
9. The feature handles sparse libraries without showing misleading rankings.
10. Results update when library or credit data changes.
11. The graph-map is useful without requiring graph-theory knowledge.
12. Ranking, filtering, and pathfinding bounds are covered by automated tests.
13. Representative results pass manual music-quality review.
14. Existing Albumary behavior is not disrupted.
15. The implementation does not require a graph database.

---

# 16. Validation Requirements

Before considering a ranking production-ready, inspect representative output.

At minimum, review:

- Top recurring contributors
- Top producers
- Top performers
- Top engineers and mixers
- Top hidden connectors
- Interactive map node selections and highlighted relationships
- Albums with unusually many credits
- Contributors with suspiciously broad reach
- Results caused by duplicate editions
- Results caused by track-only credits

Questions to ask:

- Are the results musically meaningful?
- Are primary artists overwhelming the rankings?
- Are deluxe editions creating duplicates?
- Are compilations creating false relationships?
- Are one-track performers creating noise?
- Are person identities resolving correctly?
- Are behind-the-scenes contributors represented well?
- Can every surfaced insight be explained simply?

Passing automated tests is not sufficient if the ranked results are not interesting or trustworthy.

---

# 17. Success Metrics

Potential product metrics:

- Percentage of users opening the feature
- Percentage clicking an insight card
- Percentage opening Person Detail
- Percentage using the Connection Finder
- Connection searches per user
- Repeat visits
- No-path rate
- Insufficient-credit-data rate
- Average number of follow-on explorations
- Reported credit errors
- Engagement by library size

The strongest early signal is whether users continue exploring after viewing the first insight.

---

# 18. Product Language

Preferred terms:

- Behind Your Music
- Connections
- Hidden Connector
- Recurring Contributor
- Listening Impact: removed from the Connections MVP because this feature is
  about metadata relationships, not listen frequency
- Shared Credit
- People Behind the Albums
- Explore This Connection

Avoid leading with:

- Credit intelligence
- Degree centrality
- Betweenness
- Eigenvector centrality
- PageRank
- Graph score
- Network coefficient
- Node degree

Technical terms may appear in internal documentation but should not define the user experience.

---

# 19. Final Product Definition

The MVP should make Albumary capable of saying:

> Albumary maps the creative people behind your listening. It shows who repeatedly shapes your favorite albums, how seemingly unrelated records are connected, and where those relationships can lead next.

The product should compete on personalized interpretation, not on having the largest credit database or the most complex graph.
