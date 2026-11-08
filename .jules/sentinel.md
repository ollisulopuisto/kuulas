## 2026-11-08 - HTTP response header injection in content disposition handling
**Vulnerability:** Filenames generated from user-controlled project or edit names were placed into HTTP `Content-Disposition` response headers without stripping CRLF or control characters, allowing response header injection / HTTP response splitting.
**Learning:** Quoted strings in HTTP headers (such as `attachment; filename="..."`) must not contain raw CRLF or ASCII control characters. Even when RFC 5987 percent-encoding is applied to the extended filename parameter, the fallback quoted-string parameter can break the header framing if control characters are not sanitized first.
**Prevention:** Sanitize filenames before constructing HTTP headers by stripping or replacing ASCII control characters (< 32, 127) including carriage return (`\r`) and newline (`\n`).

## 2026-11-07 - Unbounded path length in project initialization and process spawning
**Vulnerability:** New project path planning and project window launching routines accepted user-supplied directory paths without length bounds before passing them to OS filesystem and subprocess APIs.
**Learning:** Functions that validate paths for directory creation or working directories must explicitly bound string length (<= 4096 characters) before performing filesystem calls or passing them to child process startup to avoid OS-level buffer and path resolution errors.
**Prevention:** Apply the standard path validation invariant (non-empty string <= 4096 characters, no NUL bytes, absolute path without `..` traversal components) consistently to project creation and window startup paths.

## 2026-11-06 - Unvalidated export folder path and traversal vulnerability
**Vulnerability:** Export configuration and region planning accepted user-supplied folder destination paths without absolute path enforcement, size bounds, NUL-byte rejection, or directory traversal validation.
**Learning:** Background jobs and export workers that create filesystem directories and write rendered outputs based on request parameters must validate folder path boundaries at request planning time and snapshot time before job execution.
**Prevention:** Apply strict path validation (bounded non-empty string <= 4096 characters, no NUL bytes, absolute path without `..` traversal components, and verified normalized realpath) to all user-configurable export destination directory arguments.

## 2026-11-05 - Insecure discovery file handling and path traversal in control discovery
**Vulnerability:** Control discovery functions accepted project directory paths without size bounds, NUL-byte checks, or directory traversal validation, and read discovery files through symbolic links.
**Learning:** Discovery files used for local IPC and authentication tokens must validate directory path boundaries and explicitly ensure target files are regular non-symlink files prior to reading authentication material.
**Prevention:** Always validate project paths against length limits and traversal components, and verify that metadata files containing authentication tokens are not symlinks before reading.

## 2026-11-04 - Incomplete path traversal validation in media resolution handlers
**Vulnerability:** File location and replacement endpoints accepted paths containing relative segments or `..` directory traversal components before checking file presence and performing media relinking operations.
**Learning:** Checking filesystem item existence via `Path.is_file()` or `os.path.isdir()` without prior syntactic rejection of `..` traversal components or verifying resolved realpaths allows callers to refer to files outside intended boundaries or probe filesystem structure.
**Prevention:** Always enforce standard path sanitization invariants (bounded non-empty string, no NUL bytes, absolute path without `..` components, and validated `os.path.realpath` without escaping traversal) across all media resolution and filesystem query functions.

## 2026-11-02 - Missing clickjacking and MIME-sniffing protection headers
**Vulnerability:** The local HTTP server serving the web UI and project API endpoints omitted defensive framing and MIME headers, allowing third-party web origins to frame the application in an `<iframe>` or sniff content types.
**Learning:** Origin and Host header validation protects against unauthorized cross-origin state driving, but does not stop a foreign site from framing the application's UI for clickjacking attacks unless anti-framing headers (`X-Frame-Options: DENY`, `Content-Security-Policy: frame-ancestors 'none'`) are sent on all HTTP responses.
**Prevention:** Apply defensive headers (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Content-Security-Policy: frame-ancestors 'none'`) across all outgoing HTTP responses directly in the server's HTTP middleware layer.

## 2026-11-02 - Unvalidated destination folder in project copy export
**Vulnerability:** The project copy exporter accepted user-provided destination directory paths without standard path traversal checks, absolute path requirements, or length/NUL-byte bounds before attempting directory creation.
**Learning:** Functions accepting filesystem target paths from API endpoints must consistently enforce path sanitization rules (non-empty string <= 4096 characters, no NUL bytes, absolute path, no `..` traversal components, and verified `os.path.realpath`) prior to performing directory operations.
**Prevention:** Centralize or consistently apply the standard path validation invariant to all export and filesystem destination handlers.

## 2026-11-01 - Missing peer UID verification on recorder Unix domain socket
**Vulnerability:** The audio recorder supervisor listens on a Unix domain socket to manage recording sessions and control background audio capture. Although directory permissions restrict access, processes on multi-user systems or shared temporary directories could attempt connecting to the socket without peer identity verification.
**Learning:** Unix domain socket file permissions protect filesystem access at open time, but defense-in-depth requires checking the connected peer's socket credentials directly (e.g. `SO_PEERCRED` on Linux, `LOCAL_PEERCRED` on macOS) to guarantee caller authenticity.
**Prevention:** Always inspect peer credentials upon `accept()` and immediately disconnect any caller whose UID does not match `os.getuid()`.

## 2026-10-31 - Cross-Site WebSocket Hijacking bypass of HTTP middleware
**Vulnerability:** While HTTP endpoints were protected against cross-origin driving and DNS rebinding via FastAPI/Starlette `@app.middleware("http")`, Starlette HTTP middleware does not intercept WebSocket connections. As a result, `@app.websocket("/api/live")` accepted connections without validating `Host` or `Origin` headers, allowing malicious websites visited by the user to connect to `ws://127.0.0.1:<port>/api/live` and snoop on project state changes, background jobs, and playhead anchors.
**Learning:** In ASGI frameworks like FastAPI/Starlette, HTTP middleware registered via `@app.middleware("http")` only wraps HTTP request/response cycles and is completely bypassed by WebSocket routes (`@app.websocket`).
**Prevention:** Always validate `Host` against allowed loopback hosts (`_LOCAL_HOSTS`) and `Origin` against `_local_origin` directly inside the `@app.websocket` handler before calling `await ws.accept()`, rejecting unauthorized connections with `await ws.close(code=1008)`.
