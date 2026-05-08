## Problem Statement

Today the QR Code Generator backend exposes a working link shortener with QR rendering and scan analytics, but there is no user-facing UI. Anyone wanting to create a short link, customize its QR appearance, or check scan analytics has to call the API directly with `curl` or Postman. Operators cannot see at a glance which links they have created, edit a destination URL, reactivate an expired link, or download a styled QR for printing/sharing.

## Solution

Ship a single-page React/TypeScript frontend served from `frontend/` that wraps the existing backend with two views:

1. **Generator** (`/`) — a customization-rich QR creation surface where the user enters a destination URL, optionally configures expiry, picks colors / dot styles / size / format, optionally embeds a logo, and clicks Generate to mint a token. The QR is then re-rendered locally from the returned short URL using `qr-code-styling`, and the user downloads it in PNG/SVG/WebP.

2. **Dashboard** (`/dashboard`, `/dashboard/:token`) — a public, browser-scoped link manager backed by `localStorage` (no auth in Phase 1). Lists every link this browser has created with status badges (`active` / `expired` / `deleted` / `missing`), supports one-click reactivate for expired links, soft-removal-from-history for deleted ones, and per-link analytics (KPI cards, scans-by-day chart filterable by status, recent-scans table with parsed user agent).

The QR encodes the **short URL** (`{BASE_URL}/r/{token}`), not the user's original URL. Editing the destination via PATCH never invalidates a printed QR. Customization (colors, logo, ECL, size, format) is purely client-side; only the destination URL and `expires_at` round-trip to the backend.

## User Stories

1. As a marketer, I want to type a long campaign URL and click Generate, so that I get back a short, scannable QR code I can put on a flyer.
2. As a brand owner, I want to set my brand colors as the QR foreground/background, so that the printed QR matches the rest of my collateral.
3. As a designer, I want to upload my company logo onto the center of the QR, so that the QR looks branded rather than generic.
4. As a non-technical user, I want the system to automatically guarantee my QR is scannable when I add a logo, so that I don't accidentally ship a broken QR by leaving the error correction level too low.
5. As a print designer, I want to download the QR as an SVG, so that I can scale it to any size without quality loss.
6. As an operator, I want to download the QR as PNG by default, so that I can drop it into common tools (Slides, Word, email) without conversion.
7. As a power user, I want my last-chosen download format to be remembered, so that I do not have to re-pick it every time.
8. As a campaign owner, I want to set an expiry date and time on a link, so that the redirect stops working after my campaign ends.
9. As a campaign owner, I want quick presets like +7/+30/+90 days, so that I can set the most common expiries with one click.
10. As a careful editor, I want a precise date+time picker as well, so that I can expire a link at the exact campaign cut-off moment.
11. As a returning user, I want to see all the links I have created on a dashboard page, so that I can manage them after I close the tab.
12. As a returning user, I want each link's current status (active / expired / deleted / missing) clearly visible, so that I can immediately tell what is still working.
13. As a returning user, I want to filter or hide deleted links, so that my dashboard is not cluttered with old data.
14. As a forgetful user, I want a one-click "reactivate" action on expired links, so that I do not have to dig into a date picker for a common operation.
15. As a returning user, I want to click into a single link and see its full analytics, so that I can evaluate its performance.
16. As an operator, I want a top row of KPI cards (Total / Today / Success rate), so that I get the most important numbers without scrolling.
17. As an analyst, I want a 30-day scans-by-day line chart with the option to filter by status code, so that I can spot anomalies and 410 spikes.
18. As an analyst, I want a recent-scans table with timestamp, status, and human-readable user agent, so that I can sanity-check who is scanning.
19. As a privacy-conscious user, I do NOT want IP addresses exposed in the public dashboard, so that my no-auth tool cannot become an IP-leak channel.
20. As an editor, I want to update a link's destination URL after it is created, so that I can fix a typo without re-printing the QR.
21. As an editor, I want to update or clear the expiry date of an existing link, so that I can extend or revoke a campaign as plans change.
22. As an editor, I want a delete action that is reversible from my history, so that I do not permanently lose track of links I deleted by accident.
23. As a user who cleared my browser data, I want a "recover by token" input on the dashboard, so that I can re-add a known token to my history.
24. As a first-time visitor, I want the dashboard to explain what it is for when empty, so that I understand the localStorage model before I create my first link.
25. As a first-time visitor, I want to be told that history is browser-scoped, so that I am not surprised when I open the app on another device.
26. As a typing user, I want a live character counter on the URL field with a 2048 limit, so that I see the limit before I hit it.
27. As a typing user, I want the URL field to validate scheme and structure on the client, so that I get instant feedback rather than a round-trip error.
28. As a user who pastes an invalid URL, I want the backend's specific reason (private IP, malformed) surfaced as a friendly inline error, so that I know exactly why.
29. As a clicking-twice user, I want the Generate button to be disabled while the request is in flight, so that I do not accidentally mint two tokens.
30. As a user with a slow connection, I want a skeleton screen while link info or analytics are loading, so that I see where the data is going.
31. As a user submitting an action, I want a spinner inside the button (not a skeleton), so that I clearly understand "I clicked, it is working."
32. As a user, I want a subtle jitter and a confetti burst on successful generation, so that the moment of completion feels rewarding.
33. As a user with motion sensitivity, I want jitter and confetti suppressed when my OS prefers-reduced-motion is set, so that the UI does not trigger discomfort.
34. As a user with motion sensitivity, I still want a clear non-animated success signal (badge + toast), so that the success state remains obvious.
35. As a mobile user, I want the preview pane on top with sticky shrink-on-scroll, so that I can see my QR change as I tweak controls.
36. As a mobile user, I want the sidebar to collapse to a hamburger, so that I do not lose viewport width to navigation.
37. As an open-source explorer, I want a GitHub icon link in the header, so that I can inspect the code or report bugs easily.
38. As a Traditional-Chinese-speaking user, I want the entire UI in zh-TW, so that I do not have to mentally translate labels.
39. As a returning user, I want my per-link styling (colors / dot style / ECL / size) to persist across reloads, so that revisiting a link shows the look I last chose.
40. As a returning user, I am OK with re-uploading my logo after refresh, so that the localStorage quota is not consumed by image data.
41. As an error-prone user, I want a token in my history that has been removed from the backend (404) to show as "Missing" with an explicit "Remove from my history" button, so that data drift is visible rather than silently masked.
42. As an editor, I want a deleted link to show in my history with a "Deleted" badge until I explicitly remove it from history, so that I can see when I deleted what.
43. As a power user, I want bookmarkable URLs for per-link detail pages, so that I can pin or share a specific link's analytics view with myself across tabs.
44. As a careful operator, I want a clear destructive-action confirmation on Delete, so that I do not accidentally remove a live campaign link.
45. As a TanStack Query user, I want optimistic UI updates for PATCH actions to feel snappy, while remaining safe to revert if the server rejects.

## Implementation Decisions

### Architecture

- **Stack:** Vite + React + TypeScript, served from `frontend/`. shadcn/UI (Radix primitives) + Tailwind for visual layer. Framer Motion for transitions. React Router for navigation.
- **Server state:** TanStack Query v5. Per-token query keys: `['link', token]`, `['analytics', token]`. A factory module centralizes keys to keep cache invalidation in one place.
- **Form state:** **TanStack Form + zod** (not react-hook-form). A small custom `<FormField>` wrapper bridges shadcn primitives, since shadcn's built-in `<Form>` is RHF-shaped. zod schemas are the single source of truth shared between the form and the API client.
- **Networking:** Axios with a response interceptor that normalizes every non-2xx into a typed `ApiError = { status, code, detail, isNetwork }`. The interceptor never _suppresses_ errors — only normalizes; per-call handlers decide rendering.
- **Routing:** `/` (Generator), `/dashboard` (overview list + global empty state), `/dashboard/:token` (per-link detail with edit + delete + analytics).

### Data flow & token semantics

- Frontend POSTs `{url, expires_at}` to `POST /api/qr/create`. The returned token is appended to a localStorage history.
- The QR is re-rendered locally from the **short URL** `{BASE_URL}/r/{token}` using `qr-code-styling`. The QR pixels never depend on the user's original URL — only on the token. PATCH-ing the destination URL therefore never invalidates a printed QR.
- The backend's `GET /api/qr/{token}/image` endpoint stays in the API but is unused by the customized preview path. It remains useful as a fallback or OG-image source.
- localStorage acts as the user-identity proxy in Phase 1 (no auth). Each browser sees only the tokens it has created.

### Module breakdown

Deep modules with simple interfaces that can be tested in isolation:

- **`api/client`** — Axios instance + interceptor; exports a typed client with strongly-typed endpoints. Single normalization point for `ApiError`.
- **`api/queryKeys`** — Pure factory functions that return TanStack Query keys (`linkKey(token)`, `analyticsKey(token)`). Centralizes invalidation.
- **`schemas/url`** — zod URL validator. Structural (`new URL()` parse), scheme `http`/`https`, length ≤ 2048. Used by the form _and_ re-applied by the API client before send. Defers IP/loopback rules to the backend.
- **`state/linkHistory`** — localStorage adapter for the token list. `addToken({token, originalUrl, createdAt})`, `listTokens()`, `markDeleted(token)`, `removeFromHistory(token)`. Encapsulates JSON parsing and schema versioning. Schema includes a `dismissed: boolean` flag to support the "Deleted but still in my history" UX.
- **`state/styleStore`** — Per-token style storage under `qr-style:{token}` (and `qr-style:default` for the Generator). `getStyle(token)`, `setStyle(token, style)`, `getDefault()`, `setDefault(style)`. Logo is **not** persisted (kept as in-memory ObjectURL only).
- **`qr/renderer`** — Imperative facade over `qr-code-styling`. Methods: `create(options)`, `update(options)`, `attachTo(domNode)`, `toBlob(format)`, `destroy()`. Hides upstream library complexity behind a React-friendly contract.
- **`qr/eclPolicy`** — Pure: `(hasLogo: boolean, userEcl: ECL) → { ecl: ECL, isLocked: boolean }`. Implements the spec's hard-force rule: when a logo is present, ECL is forced to `H` and the control is disabled.
- **`lib/expiresAtPresets`** — Pure: `(now: Date, preset: '+7d'|'+30d'|'+90d'|'never'|'custom') → string | null`. Deterministic with injectable clock; produces ISO-8601 with explicit `Z` for the API.
- **`lib/uaParser`** — Wraps `ua-parser-js` to return `{browser, os, device}`. Wrapping leaves the underlying library swappable.
- **`lib/motionPreference`** — Wraps Framer Motion's `useReducedMotion()`. Components consume this to gate confetti and jitter while still rendering non-animated success feedback.
- **`hooks/useLinkState`** — Composes `useQuery(linkKey(token))` and derives `LinkState ∈ {active, expired, deleted, missing}`. The `missing` case is added on top of the backend's three states to handle 404 from a token in localStorage that no longer exists in the DB.

### UX rules

- **Generate trigger:** Explicit button click only. The button is debounced/disabled while the mutation is in flight to prevent double-submit. No auto-POST on input change (the backend mints a new token per call and does not deduplicate).
- **Post-Generate:** Stay on the Generator. Confetti + jitter (gated on `prefers-reduced-motion`); QR appears; download buttons enable; "✓ Generated" badge appears on the URL field. Secondary CTAs: "View in Dashboard" → `/dashboard/:token`; "Generate another" resets the form (next click mints a fresh token; we never silently PATCH the previous one).
- **Refresh after Generate:** Fresh form, no state restoration. The token is preserved in localStorage so it remains in `/dashboard`.
- **ECL policy:** Hard-force per spec. Logo present → ECL = H, control disabled with explanatory tooltip. Logo removed → ECL becomes user-controlled again.
- **Download:** Split button "Download PNG" + dropdown caret (PNG / SVG / WebP). Last-used format sticky in localStorage. Filename: `qr-{token}.{ext}`. SVG export embeds the logo as `<image>` so the SVG remains standalone.
- **Dashboard list:** Single list, status badges (active green / expired amber / deleted gray-strikethrough). Default sort `created_at` desc. "Hide deleted" toggle defaults ON. Soft-remove from history (separate explicit "Remove from my history" button).
- **Dashboard 404 case:** Token in history but backend returns 404 → render card with "Missing" badge + "Remove from history" affordance. Never auto-purge silently.
- **One-click reactivate:** Expired cards show a small Reactivate button that opens a date picker pre-filled to `+30 days from now`; confirm → `PATCH expires_at`.
- **Empty dashboard:** Educational empty state (illustration + headline + body explaining browser-scoped history) + "Recover by token" text input as a safety net.
- **expires_at:** Hidden under collapsible "Advanced" on the Generator. Default `null` (never expires). Picker = date+time + quick chips (+7 / +30 / +90 / Never). Local input → UTC API. Always exposed on the dashboard detail edit form.
- **URL validation:** Frontend mirrors structural + scheme + 2048 cap rules client-side. Live counter `127 / 2048`. Backend rejection (private IP, etc.) surfaces as a friendly inline form error from the 422 detail.
- **Mobile (`< md`):** Stacked layout, **preview pane on top, sticky shrink-on-scroll**. Sidebar collapses to hamburger. Breakpoints: `md` 768px (pivot to side-by-side), `lg` 1024px (full 60/40), `max-w-[1200px]` container.
- **Reduced motion:** Confetti and jitter gated by `useReducedMotion`. Functional success feedback (✓ badge, toast) always present.
- **Skeletons vs spinners:** Skeletons for `useQuery` (data fetches); inline button spinner + grayscale-disabled for `useMutation` (actions in flight).
- **Toasts (Sonner):** success 4s, warning 6s, error sticky-until-dismissed. Top-right, max 3 stacked.
- **Header:** Left wordmark "QR Code Generator", right GitHub icon → `https://github.com/PaynePew/qr_code_generator`.
- **Language:** Traditional Chinese (`zh-TW`) only. No i18n framework in Phase 1.

### Library stack

| Layer         | Pick                                     |
| ------------- | ---------------------------------------- |
| Build         | Vite + React + TypeScript                |
| UI primitives | shadcn/UI + Tailwind                     |
| Server state  | TanStack Query v5                        |
| Form state    | TanStack Form + zod                      |
| Networking    | Axios + interceptor                      |
| Routing       | react-router-dom                         |
| QR rendering  | qr-code-styling                          |
| Toasts        | Sonner                                   |
| Color picker  | react-colorful                           |
| Date picker   | shadcn `<DatePicker>` (react-day-picker) |
| Date utils    | date-fns v3                              |
| File upload   | react-dropzone                           |
| Charts        | Recharts                                 |
| Confetti      | canvas-confetti                          |
| Animation     | Framer Motion                            |
| UA parsing    | ua-parser-js                             |

### API contracts (existing backend, no changes for Phase 1)

- `POST /api/qr/create` — body `{url, expires_at?}` → `{token, short_url, qr_code_url, original_url}`
- `GET /api/qr/{token}` → full link info incl. derived `status`
- `PATCH /api/qr/{token}` — body `{original_url?, expires_at?}` → updated link info
- `DELETE /api/qr/{token}` → terminal soft-delete
- `GET /api/qr/{token}/analytics` → `{total_scans, scans_by_day, recent_scans}`

### Backend follow-ups (out of scope for this PRD but worth tracking)

- Mirror the 2048-char URL length cap on the backend so frontend/backend rules cannot drift.
- Add `scan_count` to `GET /api/qr/{token}` so the dashboard list does not need to fan out N analytics calls just to show counts.

## Testing Decisions

A good test exercises the **observable contract** of a module — its inputs, outputs, and externally visible side effects — not the internal structure. Tests should not break when the implementation is refactored without changing behavior. Mocks are reserved for genuine boundaries (network, DOM, time); pure logic should be tested directly.

### Modules tested in Phase 1

The four highest-value pure-logic modules:

1. **`schemas/url`** — zod validator. Test valid http/https URLs of varying length, invalid schemes (`ftp://`, `javascript:`, no scheme, bare domain), exactly-at-cap (2048) and over-cap inputs, malformed inputs. Pure function — no setup, no async.

2. **`state/linkHistory`** — localStorage adapter. Tests run against a fake localStorage. Cover: add/list round-trip, idempotent add, mark-deleted preserves entry but flips state, remove-from-history fully purges, schema-version mismatch handling (migration or fallback to empty), behavior when localStorage is full or unavailable.

3. **`state/styleStore`** — same shape as linkHistory. Per-token round-trip, default preset fallback when no per-token entry exists, namespace separation between `qr-style:default` and `qr-style:{token}`, behavior when JSON is corrupt.

4. **`qr/eclPolicy`** — pure rule. Exhaustive table-driven test: cross-product of `hasLogo ∈ {true, false}` × `userEcl ∈ {L, M, Q, H}`. Verifies the locked output is always H when `hasLogo` is true, and that user choice is preserved when no logo.

### Testing approach

- **Test runner:** Vitest (Vite-native, fast, Jest-API-compatible).
- **Assertion style:** plain `expect()` matchers; no chai/jest extras.
- **Fake localStorage:** a 30-LOC in-memory mock conforming to the `Storage` interface, swapped in via dependency injection or vitest globals.
- **No DOM tests in Phase 1** — `qr/renderer` and React hooks are deferred until integration tests exist.

### Prior art in the codebase

The existing backend `tests/` directory uses pytest with the same philosophy: pure-logic modules (`url_validator`, `token_generator`, `link_state`, `analytics`) are tested directly without HTTP fixtures, while integration concerns (`router`) get their own test file. The frontend mirrors that split: `schemas/url` and `qr/eclPolicy` are pure-logic equivalents of `url_validator` and `link_state`.

## Out of Scope

- **Authentication and per-user history.** The localStorage model is the explicit Phase-1 substitute.
- **Backend changes.** The PRD assumes the existing API surface is sufficient. The two follow-ups (URL length cap, scan_count) are tracked separately and not blockers.
- **Logo persistence across refresh.** Logos remain in-memory ObjectURLs; users re-upload after a hard reload. IndexedDB-based logo persistence is Phase 2.
- **Multi-language support.** zh-TW only. No i18n framework.
- **Geographic / referrer analytics.** Backend does not capture them.
- **IP visibility in the scan table.** Hidden until auth exists, to prevent the public dashboard becoming an IP-leak channel.
- **Cross-link aggregate analytics.** Each link's analytics is per-token; "all my links combined" KPIs are deferred.
- **Tests for `qr/renderer`, `useLinkState`, `lib/expiresAtPresets`, `lib/uaParser`, `api/client` interceptor.** Covered loosely via integration tests in a later phase.
- **English (or other) language support.** zh-TW only in Phase 1.
- **Deep customization beyond the spec** (e.g., gradient editors, custom dot-shape uploads, custom corner-eye SVGs).

## Further Notes

- The QR encodes the **short URL**, never the original URL. This is the load-bearing decision: it allows PATCH-ing the destination without ever invalidating a printed QR. Anyone implementing must preserve this property.
- `qr-code-styling` is an imperative library that mounts to a DOM node. The `qr/renderer` module exists to keep that imperativeness contained — React components should never call `qr-code-styling` directly.
- The `dismissed` flag in `state/linkHistory` is what enables the "soft remove from history" UX. Deleting a link via the API and removing it from history are two separate user-visible actions.
- The "Missing" link state (404 from a token in history) is invented by the frontend on top of the backend's three states (active/expired/deleted). It only exists in `useLinkState`'s output, never in API payloads.
- The 2048 URL length cap is enforced **only on the frontend** in Phase 1. A backend-side mirror is the highest-priority follow-up so the rules cannot drift over time.
- `prefers-reduced-motion` is honored via Framer Motion's `useReducedMotion()` hook for both confetti and jitter. Functional success feedback (✓ badge, toast) is always rendered regardless.
