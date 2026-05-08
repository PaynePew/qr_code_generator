# QR Code Generator Prototype

## System Requirements

Build a dynamic QR code system where:

- Users submit a long URL and get back a short URL token + QR code image
- The QR code encodes a short URL that redirects (302) to the original URL via your server
- Users can modify the target URL after QR code creation
- Users can delete a QR code (soft delete)
- Users can optionally set an expiration timestamp on create or update
- Deleted or expired links return appropriate HTTP status codes
- URL validation: format check, normalization, malicious URL blocking

## Design Questions

Answer these before you start coding:

1. **Static vs Dynamic QR Code:** Why does this system use dynamic QR codes (encode short URL) instead of static (encode original URL directly)? When would you choose static instead?
   - The redirect target lives in the backend, so you can update the long URL without reissuing the QR asset—the encoded short URL stays constant. A shorter payload lowers QR module density, which generally improves decode reliability on camera hardware. Because each scan resolves through your redirect endpoint first, you can emit telemetry (scan counts, timestamps, coarse geo from IP or client hints) and surface those metrics back to the user.

2. **Token Generation:** How will you generate short URL tokens? What happens when two different URLs produce the same token? How does collision probability change as the number of tokens grows?
   - To generate unique tokens, we use a combination of **Hashing** and **Encoding**. First, we take the long URL and append a **Secret** (a server-side private key) and a **Nonce** (a retry counter or random value) to increase **Entropy**. We then pass this string through a cryptographic hash function like **SHA-256** to ensure a **deterministic** and fixed-length output.
   - To make the token URL-friendly and concise, we encode the hash output into **Base62** (consisting of [0-9A-Za-z]). Finally, we truncate the result to the first **N characters** (e.g. N = 7). The choice of N determines our **Key Space**; for instance, 62^7 provides over 3.5 trillion unique combinations, significantly reducing the probability of collisions.
   - Even with a large key space, collisions can occur due to the **Birthday Paradox**. To handle this, we enforce a **UNIQUE constraint** on the toke column in the database. Our workflow follows an **Optimistic Insertion** pattern.
     1. Attempt to `INSERT` the generated token into the database.
     2. If a **Conflict (Unique Violation)** is triggered, we increment the **Nonce**.
     3. Regenerate a new token using the updated Nonce and **retry** the insertion.
     4. This ensures that even for the same input URL, we can eventually produce a unique, non-colliding token.

3. **Redirect Strategy:** Why 302 (temporary) instead of 301 (permanent)? What are the trade-offs for analytics, URL modification, and latency?
   - We prefer **HTTP 302 (Found/Temporary Redirect)** over **HTTP 301(Moved Permanently)** primarily for **analytics and control**.
     1. **Analytics & Telemetry**: A **301 redirect** is cached by the browser. Subsequent clicks will bypass servers entirely, making it impossible to track real-time click metrics, geographic data, or referrer information. With a **302 redirect**, the browser must consult our server for every click, allowing for precise data collection.
     2. **Link Mutability**: Short URLs often need to be updated(e.g., correcting ad typo in the destination or rotating marketing links). Since browsers cache 301 redirects indefinitely, updating a target URL becomes nearly impossible once it's cached on the user's device. 302 provides the flexibility to modify the destination URL at any time.
     3. **Latency Trade-off**: The primary downside of 302 is the **network overhead**. While a 301 redirect allow the browser to jump directly to the destination from the second visit onwards, a 302 redirect forces an additional **Round Trip Time (RTT)** to our shortening service for every single access.

4. **URL Normalization:** What normalization rules do you need? Why is `http://Example.com/` and `https://example.com` potentially the same URL?
   - The goal of **URL Normalization** (or canonicalization) is to deduplicate URLs before hashing. Without it, the same destination would consume multiple tokens, washing storage and splitting analytics data.
     1. **Lowercasing the Host**: `Example.com` and `example.com` are identical because domain names are **case-insensitive** per DNS standards.
     2. **Removing Default Ports**: `example.com:80` is functionally identical to `example.com`. Removing these reduces string noise.
     3. **Handling Trailing Slashes**: `://example.com` vs `://example.com`. Most web servers serve the same content for both, so we enforce a consistent format to avoid duplicate tokens.
     4. **Sorting Query Parameters**: `?a=1&b=2` and `?b=2&a=1` typically produce the same page. Alphabetizing keys ensures the generated hash remains identical.
     5. **Scheme Normalization**: while **HTTP** and **HTTPS** are technically different protocols, we often normalize them to `https://` by default to consolidate analytics, as most modern sites redirect traffic to the secure version anyway.

5. **Error Semantics:** What should happen when someone scans a deleted link vs a non-existent link? Should the HTTP status codes be different?
   - When a user accesses a broken link, the system should return different HTTP status codes depending on the **resource's history** provide clear signals to both users and search engines.
     1. **Non-existent Links (404 Not Found)**: If a token has never existed in our database, we should return a **404 Not Found**. This indicates a potential typo in the URL or a malicious scan of our key space. It tells the client that the resource is missing and there is no record of it ever being here.
     2. **Deleted/Expired Links (410 Gone)**: If a link was previously active but has been manually deleted or has expired, we should return a **410 Gone**. This is a more specific and 'stronger' status than 404. It explicitly informs crawlers (like Googlebot) that the resource is **permanently removed** and should be purged from their index immediately.
   - Why distinguish them?
     1. **SEO Efficiency**: Using **410** allows search engines to clean up their index faster than a 404, preventing unnecessary crawl budget waste on dead links.
     2. **User Experience**: From a frontend perspective, we can display a more helpful message for a 410 ("This promotion has ended") versus a generic 404 ("Page not found").

## Verification

Your prototype should pass all of these:

```bash
# Create a QR code
curl -X POST http://localhost:8000/api/qr/create \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
# → 200, returns {"token": "...", "short_url": "...", "qr_code_url": "...", "original_url": "..."}

# Redirect
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/{token}
# → 302

# Get info
curl http://localhost:8000/api/qr/{token}
# → 200, returns token metadata

# Update target URL
curl -X PATCH http://localhost:8000/api/qr/{token} \
  -H "Content-Type: application/json" \
  -d '{"url": "https://new-url.com"}'
# → 200

# Redirect now goes to new URL
curl -o /dev/null -w "%{redirect_url}" http://localhost:8000/r/{token}
# → https://new-url.com

# Delete
curl -X DELETE http://localhost:8000/api/qr/{token}
# → 200

# Redirect after delete
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/{token}
# → 410

# Non-existent token
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/INVALID
# → 404

# QR code image
# (create a new one first, then)
curl -o /dev/null -w "%{http_code} %{content_type}" http://localhost:8000/api/qr/{token}/image
# → 200 image/png

# Analytics
curl http://localhost:8000/api/qr/{token}/analytics
# → 200, returns {"token": "...", "total_scans": N, "scans_by_day": [...]}
```

## Suggested Tech Stack

Python + FastAPI recommended, but you may use any language/framework.
