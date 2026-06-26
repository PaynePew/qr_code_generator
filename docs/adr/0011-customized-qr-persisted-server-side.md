# ADR 0011: Customized QR images are persisted server-side (partially reverses ADR 0004)

**Status:** Accepted

## Context

ADR 0004 kept QR customization (colour, dot style, ECL, size, logo) entirely
client-side: the backend stored no styling, and a customized QR lived only in the
browser — logos were lost on refresh and nothing survived across devices. Two things
make that untenable now: (1) the product requires a user's customized QR to come back
exactly as they made it the next time they open the token, and (2) Phase 1 introduced
per-user accounts, so customization tied to one browser's `localStorage` is wrong —
logging in from another device should show the same customized QRs (the same way Link
History had to move server-side).

## Decision

Persist a Link's customization server-side, per owner. We store the **recipe and the
result**, not a server-side styling engine:

1. **Rendered composite** (the styled QR with any logo baked in) → object storage (S3).
   This is what the public image URL serves for a customized Link.
2. **Style params** (the recipe: colours, dot style, format, and a logo reference)
   → the database, so the customization is re-editable, not merely viewable. Render
   resolution is fixed and the error-correction level is derived (raised when a logo is
   present), so neither is a user-facing knob.
3. **Uploaded logo** (if any) → object storage, referenced by the params, so a re-edit
   can recompose without re-uploading.

The frontend still renders the QR client-side with `qr-code-styling` (ADR 0004's
Option 3 is retained); the backend stores the exported result and the recipe rather
than growing its own styling pipeline.

## Consequences

- **Unlocks what ADR 0004 gave up:** the customized QR is now URL-addressable —
  OG/social previews, email/print embedding, and cross-device display all work.
- **ADR 0004 is partially superseded:** its *persistence* stance is reversed; its
  *client-side rendering* stance is retained. (ADR 0004's Status should be flipped to
  "Partially superseded by ADR 0011" when Phase 4 is implemented.)
- **Stored composite is public and immutable** — written under a versioned key so a
  CDN (Phase 8) can cache it forever with no purge race; re-styling writes a new
  version and old ones are reaped by an S3 lifecycle rule. Style params and the raw
  logo are owner-only.
- **The vanilla server-rendered PNG remains the fallback** for Links that were never
  customized; `GET /api/qr/{token}/image` serves the stored composite when one exists,
  else regenerates vanilla as today.
- **Uploads go through a validating backend proxy, not presigned-PUT direct to S3.**
  Presigned direct upload pays off for large files, high upload volume, or serverless
  backends — none of which apply here (QR/logo assets are tiny, customization is
  low-frequency, the backend is a normal VPS). Proxying lets the backend validate the
  bytes (real image, size cap, EXIF strip) and write the DB row atomically. Recorded so
  the appealing-but-unjustified presigned option is not re-proposed later.

## Amendment (2026-06-26): error-correction level is a user-facing knob

Decision 2 above recorded that the error-correction level was "derived (raised
when a logo is present), so neither [resolution nor ECL] is a user-facing knob."
The shipped customization UI instead exposes **ECL as an owner choice** (L / M / Q
/ H, default M), auto-locked to H only when a logo is present. That divergence was
reviewed and the UI behaviour was kept: ECL is a legitimate customization choice —
it trades QR density for scan robustness, which a user printing onto varied media
may reasonably want to control. CONTEXT.md §Customization is updated to match.
**Render resolution remains system-managed** (still not a user knob).
