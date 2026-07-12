# Paid Launch Readiness Audit — July 2026

## Decision

**D — Not ready for external growth.**

Albumary has a compelling album-first product idea and differentiated analytics,
but production testing found a critical ownership boundary failure, a broken
first-value workflow, and an unavailable advertised import source. Do not begin
broad marketing or accept payment until the launch-blocking issues below are
resolved and independently retested.

## Scope and method

This was a production, black-box audit of `https://app.albumary.net`. The review
used only visible browser behavior and synthetic profiles (`Inigo`, `Inigo 2`,
and `Inigo 3`); it did not inspect source, configuration, logs, databases, or
network internals. No existing profile data was modified.

Tested areas included public acquisition pages, public profiles, desktop and
mobile layouts, keyboard navigation, profile creation, empty states, manual
album creation, Spotify OAuth/sync, Last.fm import preview, recovery/deep links,
invalid routes, and visible account/data-management surfaces.

## Verified launch blockers

### 1. Stored Spotify access can be operated from a clean browser

`Inigo 3` was created and connected to Spotify in one browser. A separate clean
browser then opened `/inigo-3/discovery`, showed **Sync Spotify**, entered
**Syncing...**, and completed with a success toast. No account identity or
ownership check was presented.

This is a verified authorization and privacy failure. A public profile URL must
not be sufficient to use a stored third-party connection.

Tracking issue: [#17](https://github.com/429jbatty/spotify_tracker/issues/17).

### 2. First manual album creation does not complete or fail recoverably

Two independent first-album submissions stayed on disabled **Adding...** for
more than 40 seconds and did not appear in the Library:

- Talking Heads — *Remain in Light* on `Inigo`
- Tyler, The Creator — *Flower Boy* on `Inigo 3`

No success, error, timeout, retry, or recovery state was shown.

Tracking issue: [#18](https://github.com/429jbatty/spotify_tracker/issues/18).

### 3. Last.fm import is unavailable in production

Last.fm Preview returned `LASTFM_API_KEY is not configured.`. This is an
advertised onboarding path and the error exposes configuration-oriented wording
to users.

Spotify ZIP upload lifecycle testing remains incomplete: a valid synthetic ZIP
was prepared but browser file-access policy prevented upload from the audit
environment. The application still needs a production smoke test covering ZIP
validation, progress, refresh recovery, retry, review, and cleanup.

Tracking issue: [#19](https://github.com/429jbatty/spotify_tracker/issues/19).

## High-priority readiness gaps

### Ownership, recovery, and onboarding

Profile creation asks only for a profile name. It has no visible identity,
ownership claim, recovery, privacy choice, Terms/Privacy acknowledgement, or
public/read-only distinction. Empty profiles are absent from Browse Profiles
after Switch user, leaving users dependent on remembering their URL. New users
land on zero-value analytics; empty Library and Releases views provide little
guidance.

Tracking issue: [#20](https://github.com/429jbatty/spotify_tracker/issues/20).

### Privacy, legal, support, and data controls

No discoverable Privacy, Terms, contact, support, status, export, profile
deletion, account deletion, visibility, or Spotify-disconnect controls were
found. `/privacy` is interpreted as a profile slug. Spotify's consent screen
identifies the application as **AOTW** rather than Albumary.

Tracking issue: [#21](https://github.com/429jbatty/spotify_tracker/issues/21).

### Mobile and accessibility

At 390×844, the Release Dates chart is clipped outside the viewport and the
Library table is severely compressed. Keyboard focus is inconsistent on several
styled controls; profile pages lack a clear main landmark and sometimes have
competing level-one headings.

Tracking issue: [#22](https://github.com/429jbatty/spotify_tracker/issues/22).

### Large-library performance and acquisition metadata

Jacob's Library rendered all 1,279 rows and images at once, producing a roughly
93,658px document; one run took about 8.7 seconds to become usable. Every
audited route used the title `My Music`; the landing page had no observed
description, canonical, or Open Graph metadata. The landing hero's album total
also differed from the live directory total.

Tracking issue: [#23](https://github.com/429jbatty/spotify_tracker/issues/23).

## Product strengths

- The value proposition is clear and aligned with album-focused listeners.
- Public profiles demonstrate real value before signup.
- Discovery/replay analysis, metadata, artwork, release-era analysis, and
  credit connections are differentiated and visually strong on desktop.
- Deep links and refresh persistence worked on tested profiles.
- Invalid profile and invalid-route states offer clear recovery.

## Ordered path to readiness

1. Resolve authenticated ownership and revoke or safely migrate existing Spotify
   connections.
2. Make manual first-album creation reliably complete or fail with a visible,
   idempotent retry path.
3. Restore Last.fm and complete end-to-end production import testing.
4. Add activation-first onboarding and recoverable owned-profile navigation.
5. Add privacy, legal, export/deletion, integration management, and support
   surfaces.
6. Repair mobile core views and scale large-library rendering.
7. Improve public sharing metadata and validate willingness to pay before
   building billing.

## Minimum conditions for the next stage

Before inviting nontechnical users, verify that anonymous users cannot operate
another profile's mutations or integrations, first value is reachable through
manual add and each advertised import, empty states guide users forward,
mobile core flows work, and basic privacy/support surfaces are live.

Before accepting payment, additionally verify account ownership, export and
deletion, connected-account management, subscription/cancellation/refund
operations, support coverage, and operational controls outside this black-box
review (backups, monitoring, access control, incident response, and test
coverage).

## Residual audit state

The synthetic profiles remain because no user-facing deletion control was
available. No synthetic album persisted and no Last.fm import session was
created. `Inigo 3` remains connected to the Spotify account used for testing;
revoke the **AOTW** authorization in Spotify account settings unless it is
needed for follow-up work.
