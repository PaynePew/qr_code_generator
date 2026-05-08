# ADR 0004: QR customization is rendered client-side; the backend stores no styling

**Status:** Accepted

## Context

PRD #6 introduces a feature-rich QR customization surface (foreground/background colors, embedded logos, error correction level, dot styles, size, multi-format export). The existing backend, however, accepts only `{url, expires_at}` on `POST /api/qr/create` and renders a vanilla black-and-white PNG via `qr_generator.generate_qr_png`. Three structural options were considered for closing this gap:

1. **Standalone client tool.** Frontend never calls the backend; types in arbitrary text and produces a styled QR locally. Sacrifices tokens, short URLs, expiry, and scan analytics — i.e., the entire backend value.
2. **Extend the backend with styling fields.** Add columns for color, logo blob, ECL, etc. The backend image endpoint regenerates with the stored styles. Customized QRs are URL-addressable (useful for OG images, sharing). Requires schema migration, blob storage for logos, and rework of the image pipeline.
3. **Client-side styling on top of an unchanged backend.** Frontend mints a token via the existing API, then uses a browser library (`qr-code-styling`) to render the *short URL* with whatever local styling the user has chosen. Customization never touches the backend.

The product value of the existing backend is the **link shortener + scan tracking + expiry** behavior, which all three options need to preserve or replace. Customization aesthetics, in contrast, are a rendering concern.

## Decision

Take Option 3. The frontend always renders the QR client-side from the **short URL** `{BASE_URL}/r/{token}`. The backend remains unaware of foreground/background color, logos, ECL, dot style, size, and export format. `POST /api/qr/create` continues to accept only `{url, expires_at}`. `GET /api/qr/{token}/image` continues to return a vanilla PNG and is retained as a fallback / OG-image source, not as the primary preview.

The QR encodes the short URL, **not** the user's original URL. This is load-bearing: PATCH-ing the destination URL changes neither the token nor the short URL, so it changes neither the QR pixels — a printed QR remains valid forever even as its destination is edited.

## Consequences

- **No backend churn for Phase 1.** The frontend ships against the existing API surface unchanged. Feature delivery is fastest along this axis.
- **Customization is browser-scoped, not URL-addressable.** Two browsers viewing the same token render the QR with whatever local styling each has stored. Sharing "my customized QR for token X" is done by exporting the file (PNG/SVG/WebP), not by sharing a URL.
- **No OG image / social preview support for customized QRs.** A `<meta property="og:image">` for a short link can only point to the unstyled `GET /api/qr/{token}/image`. Acceptable in Phase 1; reconsider if social-share preview ever becomes a feature.
- **Logos do not survive across devices.** Logo persistence is in-memory only (per ADR-adjacent decision in PRD #6); even on the same browser, a refresh loses the logo. Per-token color and dot-style choices do persist in `localStorage`.
- **Reversibility is non-trivial.** Migrating to Option 2 later means: schema migration to add styling columns, blob storage for logos, image-pipeline rework to render styled output server-side, a story for tokens created before the migration that have no stored style. The cost is meaningful and is the reason to record this decision now.
- **Editing the destination URL never invalidates a printed QR.** This is treated as a feature and must be preserved by future changes.
- **Scan analytics still work.** Because the QR encodes the short URL, scans continue to flow through `/r/{token}` and are recorded as Scans. Choosing Option 1 would have lost this entirely.
