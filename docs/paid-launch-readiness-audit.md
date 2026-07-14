# Paid Launch-Readiness Audit Plan

## Purpose

Conduct a black-box, evidence-based audit of Albumary's publicly visible
website and user-facing functionality to decide whether it is ready to acquire
more users and charge for the product. The audit must produce a clear launch
recommendation and an ordered, high-value path to readiness—not just a list of
bugs or generic best practices.

## Scope and guardrails

- Production URL: `https://app.albumary.net`
- This is a read-only, black-box audit. Do not inspect repository code, local
  files, source maps, deployment configuration, server logs, databases,
  network responses beyond what is normally visible in browser developer tools,
  or private implementation details. Evaluate only the website's visible
  behavior and functionality.
- Do not modify production data or configuration unless the owner explicitly
  authorizes a follow-up change.
- Do not use real customer accounts or credentials. Use a dedicated test
  account and clearly labeled synthetic test data when authentication is
  needed.
- Do not purchase anything; delete non-test data; send messages; run
  destructive security testing; or attempt to bypass access controls.
- Passive security and privacy checks are in scope.
- Distinguish verified behavior, inferences, and unknowns.
- Document findings as work proceeds so that partial results remain useful.

## Agent coordination

Use one lead agent to own scope, safety, evidence quality, and the final report.
The lead agent should delegate bounded, independent work to focused subagents
when doing so improves coverage or speed. The lead agent must consolidate all
subagent findings, remove duplicates, resolve conflicts, and make the final
launch recommendation itself.

Suggested subagent assignments, adjusted to the access actually available:

- Public-product, positioning, and conversion review
- Mobile, visual-quality, and accessibility review
- New-user onboarding and activation review
- Authenticated core-workflow, import, and persistence review using the test
  account
- Reliability, error-state, and passive security/privacy review
- Paid-product, legal-surface, support, retention, and growth review

Every subagent must remain within the black-box guardrails, report only
evidence it observed, and return a structured finding list to the lead agent.
Do not let subagents change the site, inspect code, or issue a final verdict.

## Product context

Albumary is a personal album-listening tracker. It imports listening history,
tracks completed album listens, enriches albums with MusicBrainz metadata and
artwork, and shows how a person's musical taste changes over time. Public
profiles include discoveries, replays, release-era trends, credits, and
connections between albums.

Before beginning, obtain or record the following owner-supplied context when
available:

- Target customer and market
- Primary value proposition
- Current and proposed free/paid plans and pricing
- Dedicated test account credentials and allowed test data
- Supported import sources and Spotify connection setup
- Billing provider and test-mode access, if billing exists
- Analytics, error-monitoring, deployment, backup, and support documentation

## Required route and workflow coverage

Start with these public routes, then use the UI to discover additional routes:

- `https://app.albumary.net/`
- `https://app.albumary.net/jacob`
- `https://app.albumary.net/jacob/discovery`
- `https://app.albumary.net/jacob/library`
- `https://app.albumary.net/jacob/releases`
- `https://app.albumary.net/jacob/connections`
- An individual album-detail page discovered through the UI

Where supported and authorized, audit:

- Registration, sign-in, sign-out, session expiry, and account recovery
- First-time onboarding and profile creation/editing
- Listening-history imports and Spotify connection/tracking
- Import progress, failures, retries, cancellation, and recovery
- Empty, loading, success, error, and returning-user states
- Search, filtering, sorting, navigation, and deep links
- Editing and deleting the test user's own data
- Account settings, export, and deletion flows
- Subscription, upgrade, downgrade, cancellation, failed payment, and billing
  entitlement states, if present
- Privacy, terms, pricing, contact, help, and support surfaces
- Invalid URLs, nonexistent users, unauthorized access, network failures, and
  refresh/navigation persistence

Test both desktop (approximately 1440x900) and mobile (approximately 390x844),
as well as keyboard-only navigation. Test slow or unreliable network behavior
where tooling permits.

## Audit phases

Work in phases. At the end of each phase, report what was tested, verified
findings, unknowns, and the next planned phase. Do not declare launch readiness
until all applicable phases are complete.

### Phase 1: Public-product and acquisition audit

Evaluate the landing page and public profiles as a prospective customer:

- Ten-second comprehension of purpose and value
- Differentiation from alternatives such as Last.fm, stats.fm, ListenBrainz,
  Musicboard, Rate Your Music, spreadsheets, and Spotify Wrapped
- Target-customer clarity, calls to action, trust, and conversion friction
- Mobile UX, visual quality, accessibility, SEO, titles, metadata, and link
  previews
- Whether the product demonstrates value before registration

### Phase 2: New-user activation and core workflow audit

Use the dedicated test account to evaluate:

- Registration through first meaningful outcome
- Onboarding clarity and time to first value
- Import and Spotify-connection clarity
- Long-running job status, failure visibility, retry/recovery, and persistence
- Core profile, library, discovery, release, credit, and connection experiences
- Navigation, data mutation feedback, refresh behavior, and error handling

### Phase 3: Black-box reliability, trust, and operations audit

Evaluate only externally observable behavior and public-facing operational
surfaces:

- Authentication and authorization behavior, including visible cross-user data
  isolation risks
- Input validation, upload safety, visible sensitive-data exposure, session
  behavior, and passive security/privacy risks
- Privacy disclosures, data export/deletion experiences, and third-party data
  handling as represented to users
- Import durability, external-service failure behavior, perceived performance,
  refresh behavior, and large-library performance where test data permits
- Public support, contact, status, billing, cancellation, refund, and account
  management surfaces where applicable

Explicitly list operational concerns that cannot be assessed from a black-box
website review—such as backups, monitoring, internal access controls, server
security, incident response, and automated-test coverage—as unknowns. Do not
infer that these are adequate because the visible site works.

### Phase 4: Decision and prioritized path to readiness

Reconcile browser and user-flow evidence from all subagents. Classify every
finding by severity and business impact, then deliver the final report below.

## Evaluation criteria

Evaluate all applicable areas:

1. Product and positioning
2. Acquisition and conversion
3. Activation and onboarding
4. Core workflow quality and data correctness
5. UX, visual quality, and mobile responsiveness
6. Accessibility (target WCAG 2.2 AA concerns)
7. Reliability and performance
8. Security and privacy
9. Paid-product operations, billing, and support
10. Retention, sharing, and growth loops

For every finding, record:

- Severity: Blocker, Critical, High, Medium, Low, or Polish
- Exact route and state
- Steps to reproduce, if relevant
- Observed and expected behavior
- Evidence (including screenshot or test evidence when possible)
- Why it affects revenue, trust, usability, accessibility, or reliability
- Confidence: verified, inferred, or unknown
- Recommended resolution
- Whether it blocks payment, marketing, neither, or both

## Final report requirements

### 1. Executive verdict

Choose exactly one:

- **A. Ready to market broadly and accept payment now**
- **B. Ready for a small paid beta only**
- **C. Ready for a free/invite-only beta, but not payment**
- **D. Not ready for external growth**

Explain the verdict plainly, including the strongest supporting evidence and
the concrete risks preventing a stronger verdict. Separate facts from
assumptions and unknowns.

### 2. Launch-as-is assessment

Answer these questions directly:

- If marketing begins tomorrow, what is most likely to happen?
- Will a new user understand the value, complete onboarding, reach a useful
  outcome, and feel confident paying?
- Which failures could lose trust, create support burden, or drive churn?

### 3. Prioritized readiness plan

Create one ordered list of the highest-value work needed to make Albumary ready
for paid growth. Rank by expected business value divided by effort and risk,
not by technical area. For each item include:

- Priority number and recommendation
- Problem and evidence
- User, revenue, trust, and risk impact
- Estimated effort: S, M, L, or XL
- Dependencies
- Classification: must do before charging; must do before marketing; should do
  soon after launch; or later opportunity

Do not bury launch-blocking work among polish suggestions.

### 4. Minimum paid-launch checklist

Provide separately testable completion criteria for what must be done before:

- Actively marketing the app
- Accepting payment
- Inviting nontechnical users

### 5. Launch sequence and product recommendations

Recommend:

- Work for this week, the next 2–4 weeks, and after validation
- The appropriate launch stage: private alpha, invite-only beta, paid beta, or
  public paid launch
- The smallest initial audience and why
- Who should pay first, what paid outcome/package to test, and pricing
  hypotheses
- Which assumptions require customer interviews or experiments rather than more
  engineering

### 6. Scorecard

Score each category from 0–10:

- Value proposition
- New-user activation
- Core workflow reliability
- UX and visual trust
- Mobile
- Accessibility
- Performance
- Privacy/security
- Billing and support operations
- Retention potential
- Marketing readiness
- Paid-launch readiness

### 7. Required ending

End the report using this exact format:

```text
Decision: [A / B / C / D]
Recommendation: [one or two plain-language sentences]
Do next: [the first three actions, in order]
Do not do yet: [anything that should be postponed]
Evidence confidence: [high / medium / low]
```
