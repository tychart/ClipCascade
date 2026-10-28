# AGENTS.md — fork notes for `tychart/ClipCascade`

This file is **fork-only**. It is tracked on purpose so future agent sessions (and future me)
know how this fork differs from upstream and why. It is **not** part of any upstream pull
request — exclude it (and this commit) when opening one.

- Upstream: `Sathvik-Rao/ClipCascade` (`origin`)
- This fork: `tychart/ClipCascade`, working branch `fix/desktop-autologin-reliability`
- Branch base after the 2026-10-27 migration: upstream `main` at `fed738e` (post-v3.3.1)
- Backups of the pre-migration branch: local branch `backup/autologin-3.2.0`, local tag
  `backup-autologin-320` (both point at the old 3.2.0-based tip `518ecf6`)

Long-term goal: **upstream a PR that improves the Linux desktop client** (auto-login
reliability, tray, fonts, packaging docs). See "Upstream PR plan" below before pushing.

---

## 1. What this branch is for

The Linux desktop client lost a valid session whenever the first WebSocket connect at
startup failed. The client is normally started from `graphical-session.target`, which is
reached *before* networking (DNS/Wi-Fi), so every boot ended on the login form even though
the server still accepted the stored cookie. The branch also makes the tray icon and Tk UI
fonts work out of the box on Linux, and documents a `uv`-based install plus a systemd user
unit.

Commit list on top of `fed738e` (all rebased, retitled to upstream's PR-title rules):

| Commit | Purpose |
|---|---|
| `fix(linux-gui): keep the session across restarts and slow networks` | startup retry, session probe, re-auth hook, REST timeouts, DATA `0600` |
| `fix(linux-gui): keep log history instead of truncating it on every start` | `RotatingFileHandler` (5 MiB × 2) |
| `docs: add a systemd user unit for the Linux desktop client` | `ClipCascade_Desktop/contrib/systemd/clipcascade.service` + README |
| `fix(linux-gui): warn when the tray falls back to the X11 backend` | detect `pystray` X11 fallback, log it, document PyGObject |
| `fix(linux-gui): resolve UI fonts at runtime instead of hardcoding Helvetica/Arial` | new `utils/fonts.py`, used by `gui/login.py` and `gui/info.py` |
| `docs: document a uv-native install for the Linux desktop client` | README section, `requires-python >=3.9`, ignore `uv.lock` |
| `chore: ignore local lock files created in the source tree` | ignore `clipcascade.lock` |
| `fix(linux-gui): honour pixel-sized UI fonts` | size check only for positive (point) sizes |
| `docs: record the fork's divergence from upstream in AGENTS.md` | this file (fork-only) |

---

## 2. Ground rules for agents working here

1. **Upstream is authoritative.** When a local patch and upstream disagree, prefer upstream's
   behaviour and adapt (or drop) the local patch. The user explicitly asked for this: "keep as
   much native as possible… use as much of the official code as possible". Two local changes
   were **deleted** during the 3.3.1 migration because upstream had implemented them better
   (see §3).
2. **Never re-add per-manager reconnect code.** Everything reconnect-related goes through
   `utils/reconnect.py` (`ReconnectMixin`). The only local addition there is the
   `_before_reconnect()` hook.
3. **`AGENTS.md` and its commit stay out of upstream PRs.** Everything else on the branch is
   intended to be PR-able.
4. **Don't "fix" the `save_password` security stance.** Upstream deliberately drops the stored
   password hash when encryption is enabled. This branch used to allow it; that feature was
   removed (§3). Reintroducing it needs an explicit decision because the SHA3-512 hash is
   password-equivalent.
5. Run the checks in §7 before claiming the branch works. There is no upstream test suite for
   the desktop client.

---

## 3. Migration record: 3.2.0-based branch → upstream 3.3.1 (`fed738e`)

Per-file outcome of rebasing the eight original commits. "Upstream" means the local patch was
dropped because 3.3.x already implements the intent.

| File / area | Original local change | Result after rebase |
|---|---|---|
| `stomp_ws/client.py` | local `error` attribute to fail fast instead of waiting for the full timeout | **Upstream.** Its rewrite uses `_closed`/`_ready`/`_error` events, `ping_interval`/`ping_timeout`, a STOMP handshake deadline, and malformed-frame handling. Local patch deleted. |
| `utils/request_manager.py` (CSRF) | guard for a login page without `_csrf` | **Upstream** (identical intent, same wording). Local copy deleted. |
| `utils/request_manager.py` (`timeout` param) | `timeout` argument on `get()` | **Upstream** added `timeout=None`; this branch keeps its stricter default `REQUEST_TIMEOUT` and adds a matching default to `post()`. |
| `utils/request_manager.py` (`session_is_valid`) | probe `/csrf-token` with `allow_redirects=False` | **Kept**, with `REQUEST_TIMEOUT` default, `SESSION_PROBE_TIMEOUT` at startup, and an explicit docstring for the `True`/`False`/`None` contract. |
| `utils/request_manager.py` (explicit REST timeouts) | timeouts on login GET/POST | **Kept.** Login and metadata could hang forever before. |
| `interfaces/ws_interface.py` | `relogin_callback` + `set_relogin_callback` | **Kept** (upstream has no equivalent). |
| `utils/reconnect.py` | *(did not exist)* | **New upstream file, locally extended** with `_before_reconnect()`, called from `_retry_loop` before `self.connect()`. It invokes `relogin_callback` defensively (exceptions swallowed). |
| `stomp_ws/stomp_manager.py`, `p2p/p2p_manager.py` | duplicated "call relogin, `time.sleep`, connect" block in `_on_close` | **Deleted.** Both managers now use `ReconnectMixin`; the hook runs once per retry for both. Do not re-add duplicated blocks. |
| `core/application.py` (login flow) | refactor into `_has_saved_credentials`, `_apply_login`, `_connect_with_stored_session`, `_login_interactively`, `_refresh_session` | **Kept and re-merged** onto 3.3.x's flow, including `update_checker`, `login_form.watch_updates(...)`, and the new password-clearing rule. `_apply_login` wraps the whole sequence in `try/except` so a malformed server response cannot crash the app (upstream would propagate). |
| `core/application.py` ("Store Password Locally") | allowed saved credentials with encryption enabled; added `hashed_password` requirement | **Removed.** `_has_saved_credentials()` now requires `save_password and not cipher_enabled`, matching upstream's `if cipher_enabled or not save_password: password = ""`. Consequently re-auth cannot be silent for encrypted users; they get the "log in again" notification instead. |
| `core/application.py` (startup) | retry loop with capped backoff | **Kept**, adjusted to upstream structures. Uses `SESSION_PROBE_TIMEOUT` for the probe so a dropped SYN cannot add 15 s to every retry. |
| `core/application.py` (noise filter) | drop websocket-client's `"<error> - goodbye"` ERROR lines | **Kept** in `setup_logging()`. |
| `core/config.py` | `restrict_file_permissions()` (DATA `0600`) | **Kept**, re-applied to upstream's new atomic `_save_data()`/tempfile+`os.replace` implementation, and also on `load()` to tighten files written by older versions. |
| `core/constants.py` | `STARTUP_RECONNECT_*`, `SESSION_PROBE_*`, `REQUEST_TIMEOUT`, `LOG_FILE_*` | **Kept** alongside upstream's `RECONNECT_WS_JITTER_RATIO` and `P2P_FRAGMENT_TTL_SEC`. |
| `cli/login.py`, `gui/login.py` (save-password wording) | "enables automatic login", "works with encryption" | **Removed.** Upstream's wording ("only works if encryption is disabled") is now accurate again. |
| `gui/login.py` (fonts) | `ui_font(...)` everywhere | **Kept**, applied to upstream's redesigned form (browse/clear buttons, `Path.TButton`, `HoverTooltip`) — upstream still hardcodes `Helvetica`. |
| `gui/info.py` (fonts) | `ui_font(...)` in the dialog | **Kept** (applied on top of upstream's file, which is otherwise unchanged). |
| `gui/tray.py` | `warn_if_tray_menu_is_unavailable()` | **Kept**, re-merged into upstream's macOS-aware tray (`TrayIcon`, `_stopped`, `on_main_thread`). |
| `pyproject.toml` | `requires-python >=3.9`, `tray` extra | **Kept** next to upstream's Python 3.14 pins. Justification: pinned `aiortc==1.10.0` requires ≥3.9, so `uv sync` failed for the declared `>=3.8` range. |
| `requirements_linux_gui.txt` | `PyGObject>=3.42` | **Kept** after upstream's `aiortc`/`av` conditional pins. |
| `README.md` | uv install, systemd, tray/PyGObject, log rotation | **Kept**, re-anchored to upstream's rewritten README (Steps 4.3, startup script section, logs bullet, advanced settings). |
| `contrib/systemd/clipcascade.service` | new file | **Kept** (upstream has none). |
| `utils/fonts.py` | new file | **Kept** (upstream has none). |

### Upstream changes that matter for this work (3.2.0 → 3.3.1)

Desktop client:

- **`utils/reconnect.py` — `ReconnectMixin`** (new): one cancellable retry worker per manager,
  with ±25 % jitter around `RECONNECT_WS_TIMER` (`RECONNECT_WS_JITTER_RATIO`), `_connect_lock`,
  `_retry_wake` event, `_connect_once()` on subclasses, `manual_reconnect()` resetting attempts.
  `STOMPManager` and `P2PManager` both inherit it.
- **STOMP client rewrite**: `Event`-based close/ready/error signalling, protocol ping/pong
  (25 s/20 s), malformed frames dropped instead of killing the receive loop, `ERROR` frames
  close the socket, handshake deadline, `_connect_once` recreates the client on every attempt.
- **Update checking**: new `utils/update_checker.py`; `get_version_update_status()` now returns
  `None` on failure and compares with `parse_version` (so `3.3.1 > 3.3.0`); GUI polls it via
  `LoginForm.watch_updates()`, tray shows a version item and notifies per the new
  `update_notifications` preference.
- **Device preferences**: `Config.save_preferences()` / `DEVICE_PREFERENCE_FIELDS`, atomic
  tempfile + `os.replace` save, `_saved_data` split, `update_notifications` key. Preferences save
  without a successful login.
- **Single-instance / lock file rework**: `open(path, "a+")`, PID written, kernel `flock` is
  authoritative, `atexit` + SIGTERM/SIGINT/SIGHUP handlers, file is never unlinked. The
  "run anyway?" prompt is gone.
- **macOS**: `gui/macos_tray.py`, AppKit-owned event loop, `utils/main_thread.py`,
  `Application._shutdown_macos()`, `gui/macos_self_test.py`.
- **Linux/macOS clipboard** and P2P hardening: fragment TTL, data-channel keepalive, sleep/wake
  recovery, stale-peer cleanup, `aiortc` 1.14 + `av` on Python 3.14.
- **Linux CLI**: `--gui`/`--xmode`/polling overrides in `core/constants.py`, renamed settings
  wording.

Server (relevant to client sessions):

- **Opt-in persistent sessions**: `CC_SESSION_PERSISTENCE_ENABLED` (default `false`;
  `app.session.persistence.enabled`), JDBC-backed Spring Session for H2/PostgreSQL. With it
  enabled a server restart no longer invalidates cookies; when disabled, the `SPRING_SESSION`
  table is cleared. `CC_SESSION_TIMEOUT` defaults to 525960 min (365 days).
- **Brute-force protection** (`BruteForceProtectionService`, `CC_BFA_*`): *every*
  authentication, successful or not, calls `recordAndValidateAttempt()`, which increments
  per-IP counters and can lock the account for `lockTimeoutSeconds` (default 60 s, scaling
  factor 2; `CC_MAX_UNIQUE_IP_ATTEMPTS` defaults to 15, `CC_MAX_ATTEMPTS_PER_IP` to 30). This
  is why silent re-login is throttled by
  `SESSION_PROBE_MIN_INTERVAL` (60 s) and only triggered after the probe *proves* the session
  was rejected. Never add unconditional periodic re-logins.
- Admin/Advanced UI rework: BFA tracker, online users, user details, pagination
  (`PageResponse`, `PagingUtility`), theme, `ClipCascade_Server/API.md`.

CI / release (affects how to push):

- `.github/workflows/pr-title.yml` + `.github/scripts/parse_pr_title.py` enforce PR titles:
  `<type>[!](<scope>[,<scope>...]): <description>`, joined with `+` for mixed bumps.
  Releasing types (`feat`, `fix`, `perf`) **require** a scope; non-releasing types
  (`docs`, `chore`, `refactor`, `test`, `ci`, `build`, `style`) **must not** have one.
  Scopes: `windows`, `macos`, `linux-gui`, `linux-cli`, `linux`, `desktop`, `android`,
  `server`, `all`.
- `.github/pull_request_template.md`: the **Description becomes the GitHub release notes**
  (user-facing bullets, not implementation detail). Scopes must list every changed platform.
- `version.json` tracks per-platform versions (`linux_gui` / `linux_non_gui` are separate but
  share one Linux artifact). Releases are automated; a `docs:`/`chore:` PR will not trigger one.

---

## 4. Session/auto-login design as it stands

Flow in `Application.run()` → `authenticate_and_connect()`:

1. **Stored cookie** → `_connect_with_stored_session()`. On a failed connect it probes
   `GET /csrf-token`:
   - `200` → session valid, so the failure is transient (DNS, Wi-Fi, proxy) → sleep with
     `STARTUP_RECONNECT_INITIAL_DELAY` (2 s) doubling to `STARTUP_RECONNECT_MAX_DELAY` (30 s),
     retry forever. One notification after `STARTUP_RECONNECT_NOTIFY_AFTER` (20 s).
   - `3xx` (redirect to login), `401`, `403` → session rejected → stop retrying.
   - network error → unknown → keep retrying (same as `200`).
2. **Saved credentials** (`save_password` and encryption disabled) → `_apply_login()` silently.
3. **Interactive** login form (`_login_interactively()`), looping until success.

Later, when the connection drops, `ReconnectMixin._retry_loop()` calls `_before_reconnect()` →
`Application._refresh_session()` → same probe, throttled to once per 60 s. If the session was
rejected:
- saved credentials available → re-login and reconnect silently;
- otherwise → notify once (tray "Logoff and Quit", then start again).

Known limitation: when the session is rejected and nothing can re-login, the reconnect worker
keeps retrying with the dead cookie indefinitely (it just stops notifying). This matches the
previous behaviour and upstream's worker; changing it would mean stopping the worker from the
callback, which is a bigger design change.

`_apply_login()` also enforces upstream's rule that the password hash is dropped when
encryption is enabled; the AES key in `hashed_password` is what makes auto-login unnecessary
there.

---

## 5. Linux specifics worth remembering

- **Tray**: `pystray` needs PyGObject (`gi`) for its AppIndicator backend. Without it pystray
  silently uses its legacy X11 backend, whose icon cannot open a menu at all. The client now
  logs an error naming the backend; `clipcascade.service` and the README document the Fedora
  build deps and `uv sync --extra tray`. Verify with
  `python -c "import pystray; print(pystray.Icon)"` → `pystray._appindicator.Icon`.
- **Wayland clipboard**: the Wayland monitor also imports `gi`; without it the client logs
  `Failed to start clipboard monitor` and polls XWayland (`--xmode true`).
- **Fonts**: Tk silently falls back to the bitmap `fixed` font for unknown families. Always use
  `utils/fonts.ui_font(size, [weight=], [underline=], master=<widget or root>)` for new Tk UI
  text — never `("Helvetica", n)` / `("Arial", n)`. Pixel sizes (negative) cannot be validated
  by comparing the reported size; only point sizes are compared.
- **Startup ordering**: `graphical-session.target` is reached before networking, hence the
  startup retry. The systemd unit deliberately has no `After=network-online.target`; the client
  copes on its own.
- **Runtime artifacts** in `ClipCascade_Desktop/src/` when running from source: `DATA`
  (`0600`), `clipcascade_log.log`, `clipcascade.lock`, `uv.lock` — all git-ignored. Don't
  `git add -A` that directory (this happened once during the migration and put an empty
  `clipcascade.lock` into a commit).

---

## 6. Working with upstream

- `git fetch origin && git log --oneline main..origin/main` to see new upstream work; local
  `main` is a fast-forward of `origin/main`.
- Rebase with `git rebase --onto origin/main <old-base> fix/desktop-autologin-reliability`, or
  `git rebase origin/main` while checked out.
- **Conflict hot spots** (expect all four on a large upstream change):
  1. `core/application.py` — upstream keeps editing `authenticate_and_connect()` and `run()`.
  2. `gui/login.py` — upstream reworks labels/tooltips/layout; re-apply `ui_font(...)` to any new
     `font=` argument.
  3. `README.md` — upstream rewrites the Linux install and advanced-settings sections; re-anchor
     the uv/systemd/tray/log sections by heading, not by line.
  4. `pyproject.toml` / `requirements_linux_gui.txt` — keep upstream pins, add the `tray` extra and
     `PyGObject` line after them.
- Before rebasing, create a safety ref: `git branch backup/<name> HEAD` and, if the branch is
  published, push it. The branch is force-pushed after a rebase (`--force-with-lease` is
  preferred).
- Commit messages follow the PR-title grammar even for single commits; each commit is atomic and
  should stay buildable.

### Upstream PR plan

- Include: the eight upstream-facing commits (everything except this file).
- Suggested PR title (release-relevant, `linux-gui` only):
  `fix(linux-gui): keep the session across restarts and fix the tray/font setup`
- The PR **Description** must be user-facing release notes, for example:
  - ClipCascade no longer shows the login form when the network is not up yet at login; it
    retries and connects on its own.
  - An expired or invalidated server session is refreshed automatically when the password is
    stored locally, instead of leaving a silently broken tray icon.
  - The tray icon now reports when PyGObject is missing (the icon had no menu at all in that
    case), and the Linux docs/systemd unit explain how to install it.
  - UI text no longer shrinks to an unreadable bitmap font on Tk builds without Xft.
  - Logs are kept across restarts (rotated, 5 MiB × 2) instead of being truncated.
  - A `uv` install path and a systemd user unit are documented.
- Checklist before opening: `fix(linux-gui)` scope only, description filled in, tested locally
  on Linux (GUI **and** CLI), no `AGENTS.md`, no `DATA`/logs/locks, no secrets.
- Decide explicitly whether `requires-python >=3.9` and the `tray` extra belong in the PR;
  they are packaging fixes needed for the documented `uv` flow, but they touch shared metadata.
  Note that upstream's own code uses `list | None` annotations, which need Python 3.10 at
  runtime even though the metadata still says `>=3.8` — don't try to "fix" that here.

---

## 7. Verification (no upstream desktop test suite)

Environment used for the 2026-10-27 migration: `ClipCascade_Desktop/src/.venv`
(Python 3.12.13), managed with `uv`. `python3` on the host is 3.14 and has none of the deps.
`gi`/PyGObject 3.58 and `pystray._appindicator.Icon` are present, and a display is available
(`DISPLAY=:0`; `xrandr` is missing, which only produces a harmless monitor-size warning).

Static:

```bash
cd ClipCascade_Desktop/src
.venv/bin/python -m compileall -q -x '\.venv' .
.venv/bin/python -c "import core.application; print('ok')"   # imports the GUI path + p2p/aiortc
.venv/bin/python -c "import utils.reconnect, utils.fonts, utils.request_manager; print('ok')"
git grep -n "<<<<<<<\|>>>>>>>" -- '*.py' ':!*.venv*'          # must be empty
```

Dependency resolution (needs network):

```bash
cd ClipCascade_Desktop/src && uv sync --extra tray --dry-run   # expect "Resolved NN packages"
```

Behavioural checks that were run (recreate them if needed; the harness was ad-hoc and is not
committed):

- `RequestManager.session_is_valid()` against a real local HTTP server: `200` → `True`;
  `302`/`401` → `False`; `500` → `None`; connection refused → `None`; no cookie → `False`; a
  server that accepts and never answers → `None` within the timeout.
- `Config`: saved DATA is `0600`; `hashed_password` bytes are base64-encoded; a pre-existing
  `0644` DATA is tightened on `load()`; no temp files are left behind.
- `Application._has_saved_credentials()`: `True` only for saved password + encryption disabled;
  `False` with encryption enabled, `save_password` off, or an empty password.
- `_connect_with_stored_session()` with a stub manager: 4 attempts when the server is
  unreachable, `True` once it connects, exactly one notification, `is_login_phase` cleared;
  a rejected session stops after 1 attempt and returns `False`.
- `_apply_login()`: encryption on → `hashed_password` derived, `password` cleared, cookie saved,
  still not auto-loginable; encryption off + `save_password` → hash kept and auto-loginable;
  `save_password` off → hash cleared; a login failure is returned, not raised.
- `ReconnectMixin._before_reconnect()`: invokes `relogin_callback`, swallows exceptions, is a
  no-op without a callback; both managers inherit the mixin.
- GUI (real display): `ui_font(13)` resolves to `liberation sans` (tk scaling 2.67, the exact
  192 DPI/no-Xft scenario the font fix targets); `LoginForm` and `CustomDialog` construct.
- End-to-end with a copied source tree and a `DATA` cookie pointing at a dead port: log shows
  `retrying in 2s` → `4s` → `8s`, no login form, no crash; a 302 stub makes the client log
  "The server rejected the stored session" and open the login form once; with
  `save_password` on it logs "Logging in with the saved credentials" and falls back to the form
  when the stub's JSON is incomplete.
- Log rotation: two consecutive runs both appear in `clipcascade_log.log`; `DATA` ends up `0600`.

Not verified live (needs a real ClipCascade server): STOMP/P2P reconnect after a server or
reverse-proxy restart and the silent re-auth on a genuine session expiry. The hook, probe and
retry paths are covered by stubs only. If Docker is available, the honest end-to-end test is a
local server from `ClipCascade_Server/docker-compose/`, then restart it while the client is
connected.

---

## 8. Quick reference

```bash
# GUI from source (Linux, uv venv)
cd ClipCascade_Desktop/src && .venv/bin/python main.py --gui true
# CLI instead of the tray
.venv/bin/python main.py --gui false --xmode false
# Reinstall deps after upstream changes
uv sync --extra tray
# Verify the tray backend
.venv/bin/python -c "import pystray; print(pystray.Icon)"
# Where runtime state lives when running from source
ls -l ClipCascade_Desktop/src/{DATA,clipcascade_log.log,clipcascade.lock}
```

Upstream docs to read before changing behaviour: `ClipCascade_Server/API.md`,
`.github/workflows/README.md` (release pipeline), `.github/pull_request_template.md`.
