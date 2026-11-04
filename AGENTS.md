# AGENTS.md — fork notes for `tychart/ClipCascade`

This file is **fork-only**. It is tracked on purpose so future agent sessions (and future me)
know how this fork differs from upstream and why. It is **not** part of any upstream pull
request — exclude it (and this commit) when opening one.

- Upstream: `Sathvik-Rao/ClipCascade` = remote **`upstream`** (https://github.com/Sathvik-Rao/ClipCascade.git)
- This fork: `tychart/ClipCascade` = remote **`origin`**, working branch
  `fix/desktop-autologin-reliability`
- Branch base after the 2026-11-03 migration: upstream `main` at `fd13b2b` (post-v3.4.1)
- Earlier base: upstream `main` at `fed738e` (post-v3.3.1), before that 3.2.0-based `518ecf6`
- Backup refs of pre-migration tips: local branch `backup/autologin-3.3.1` + local tag
  `backup-autologin-331` (`15a8e10`), and `backup/autologin-3.2.0` + tag `backup-autologin-320`
  (`518ecf6`)

Long-term goal: **upstream a PR that improves the Linux desktop client** (auto-login
reliability, tray, fonts, packaging docs). See "Upstream PR plan" below before pushing.

---

## 1. What this branch is for

The Linux desktop client lost a valid session whenever the first WebSocket connect at
startup failed. The client is normally started from `graphical-session.target`, which is
reached *before* networking (DNS/Wi-Fi), so every boot ended on the login form even though
the server still accepted the stored cookie. The branch also (a) keeps the xclip clipboard
backend instead of falling back to focus-stealing `wl-paste` polling, (b) makes the tray icon
and Tk UI fonts work out of the box on Linux, and (c) documents a `uv`-based install plus a
systemd user unit.

**These are separate concerns and are meant to be opened as separate upstream PRs** — see
"Upstream PR plan" in §6 for the commit → PR mapping.

Commit list on top of `fd13b2b` (all rebased, retitled to upstream's PR-title rules):

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
| `fix(linux-gui): keep the xclip backend when the clipboard is empty` | no wl-paste focus stealing on GNOME, `--xmode` is honoured, empty clipboard is not "xclip is broken" |
| `docs: document the GNOME Wayland clipboard fallback` | README clipboard table + systemd section, contrib unit notes |
| `docs: update the fork notes after the clipboard backend fix` | this file (fork-only) |

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
3. **`AGENTS.md` and its commits stay out of upstream PRs.** Everything else on the branch is
   intended to be PR-able.
4. **Don't "fix" the `save_password` security stance.** Upstream deliberately drops the stored
   password hash when encryption is enabled. This branch used to allow it; that feature was
   removed (§3). Reintroducing it needs an explicit decision because the SHA3-512 hash is
   password-equivalent.
5. Run the checks in §7 before claiming the branch works. There is no upstream test suite for
   the desktop client.
6. **Keep the fixes separable.** They are reviewed and merged as *separate* upstream PRs (§6),
   so do not fold one concern into another, do not squash the set, and keep each commit atomic
   and buildable on its own. A new fix gets its own commit (and its own PR entry in §6), not a
   ride-along on an existing one.

---

## 3. Migration record: latest rebase onto upstream 3.4.1 (`fd13b2b`)

Per-file outcome of the 2026-11-03 rebase from `fed738e` (3.3.1) to `fd13b2b` (3.4.1).
"Upstream" means the local patch was dropped because 3.4.x already implements the intent.
Everything below was re-applied by hand onto the rewritten files, not by automatic merging —
3.4.0 rewrote the tray, the login form and the whole connect path.

| File / area | Original local change | Result after rebase |
|---|---|---|
| `stomp_ws/client.py` | local `error` attribute to fail fast instead of waiting for the full timeout | **Upstream.** Its rewrite uses `_closed`/`_ready`/`_error` events, `ping_interval`/`ping_timeout`, a STOMP handshake deadline, and malformed-frame handling. Local patch deleted. |
| `utils/request_manager.py` (CSRF) | guard for a login page without `_csrf` | **Upstream** (identical intent, same wording). Local copy deleted. |
| `utils/request_manager.py` (`timeout` param) | `timeout` argument on `get()` | **Upstream** added `timeout=None`; this branch keeps its stricter default `REQUEST_TIMEOUT` and adds a matching default to `post()`. |
| `utils/request_manager.py` (`session_is_valid`) | probe `/csrf-token` with `allow_redirects=False` | **Kept**, with `REQUEST_TIMEOUT` default, `SESSION_PROBE_TIMEOUT` at startup, and an explicit docstring for the `True`/`False`/`None` contract. |
| `utils/request_manager.py` (explicit REST timeouts) | timeouts on login GET/POST | **Kept.** Login and metadata could hang forever before. |
| `utils/reconnect.py` (`relogin_callback`) | `relogin_callback` + `set_relogin_callback` used to live on `WSInterface` and every manager | **Moved onto `ReconnectMixin`.** 3.4.0 added `utils/transport_manager.py` (`TransportManager(ReconnectMixin)`), which owns the only retry worker (the inner managers' `_start_reconnect` now delegates to it via `reconnect_handler`). `TransportManager` is not a `WSInterface`, so the interface patch was dropped and `interfaces/ws_interface.py` is back to upstream. |
| `utils/reconnect.py` (`_before_reconnect`) | relogin hook before every retry | **Kept**, called from `_retry_loop()` just before `self.connect()`. It invokes `relogin_callback` defensively (exceptions swallowed). 3.4.0's own `reconnect_handler` delegation is untouched. |
| `stomp_ws/stomp_manager.py`, `p2p/p2p_manager.py` | duplicated "call relogin, `time.sleep`, connect" block in `_on_close` | **Deleted.** Both managers now use `ReconnectMixin`; the hook runs once per retry for both. Do not re-add duplicated blocks. |
| `core/application.py` (login flow) | refactor into `_has_saved_credentials`, `_apply_login`, `_connect_with_stored_session`, `_show_login_success_dialog`, `_login_interactively`, `_refresh_session` | **Kept and re-merged** onto 3.4.x: `update_checker`, `login_form.watch_updates(...)`, `login_form.cancelled` + `sys.exit(0)` *outside* Tk, the `hide_login_success_dialog` preference + "don't show again", and upstream's rule that a cookie is only usable when `not cipher_enabled or hashed_password is not None`. `_apply_login` no longer writes `server_mode`/`stun_url`/`maxsize`/`websocket_url`: `TransportManager._connect_once()` calls `utils/server_discovery.py` on every attempt. It still wraps the whole sequence in `try/except` so a malformed server response cannot crash the app (upstream would propagate). |
| `core/application.py` (`_get_ws_manager`) | returned `stomp_manager` or `p2p_manager` | **Upstream now returns `TransportManager`**; keep it that way. Everything the app/tray calls on it must exist there (`connect`, `disconnect`, `manual_reconnect`, `is_login_phase`, `is_connected`, `is_auto_reconnecting`, `get_stats`, `get_total_timeout`, `set_tray_ref`) plus `set_relogin_callback` from the mixin. |
| `core/application.py` ("Store Password Locally") | allowed saved credentials with encryption enabled; added `hashed_password` requirement | **Removed.** `_has_saved_credentials()` now requires `save_password and not cipher_enabled`, matching upstream's `if cipher_enabled or not save_password: password = ""`. Consequently re-auth cannot be silent for encrypted users; they get the "log in again" notification instead. |
| `core/application.py` (startup) | retry loop with capped backoff | **Kept**, adjusted to upstream structures. Uses `SESSION_PROBE_TIMEOUT` for the probe so a dropped SYN cannot add 15 s to every retry. |
| `core/application.py` (noise filter) | drop websocket-client's `"<error> - goodbye"` ERROR lines | **Kept** in `setup_logging()`. |
| `core/config.py` | `restrict_file_permissions()` (DATA `0600`) | **Kept**, re-applied to upstream's new atomic `_save_data()`/tempfile+`os.replace` implementation, and also on `load()` to tighten files written by older versions. |
| `core/constants.py` | `STARTUP_RECONNECT_*`, `SESSION_PROBE_*`, `REQUEST_TIMEOUT`, `LOG_FILE_*` | **Kept** alongside upstream's `RECONNECT_WS_JITTER_RATIO` and `P2P_FRAGMENT_TTL_SEC`. |
| `cli/login.py`, `gui/login.py` (save-password wording) | "enables automatic login", "works with encryption" | **Removed.** Upstream's wording ("only works if encryption is disabled") is now accurate again. |
| `gui/login.py` (fonts) | `ui_font(...)` everywhere | **Kept**, re-applied to 3.4.x's form (clipboard-limit combobox, `Path.TButton`, `HoverTooltip`) — upstream still hardcodes `Helvetica` in 14 places. The `font` import from `tkinter` is no longer needed. |
| `gui/info.py` (fonts) | `ui_font(...)` in the dialog | **Kept**, re-applied to 3.4.x's themed styles (`Dialog.TLabel`, `Header.Dialog.TLabel`, `Dialog.TButton`, `Dialog.TCheckbutton`) and the symbol/`ScrolledText` widgets. |
| `gui/tray.py` | `warn_if_tray_menu_is_unavailable()` | **Kept**, re-merged into 3.4.x's per-platform tray (`gui/linux_tray.py`, `gui/windows_tray.py`, `gui/macos_tray.py`, `gui/tk_owner.py`). Upstream still picks plain `pystray.Icon` for Linux when neither the GTK nor the AppIndicator backend imported, so the patch still fires (`pystray._xorg.Icon.HAS_MENU is False`). |
| `pyproject.toml` | `requires-python >=3.9`, `tray` extra | **Kept** next to upstream's Python 3.14 pins. Justification: pinned `aiortc==1.10.0` requires ≥3.9, so `uv sync` failed for the declared `>=3.8` range. |
| `requirements_linux_gui.txt` | `PyGObject>=3.42` | **Kept** after upstream's `aiortc`/`av` conditional pins. |
| `README.md` | uv install, systemd, tray/PyGObject, log rotation | **Kept**, re-anchored to upstream's rewritten README (Steps 4.3, startup script section, logs bullet, advanced settings). |
| `contrib/systemd/clipcascade.service` | new file | **Kept** (upstream has none). |
| `utils/fonts.py` | new file | **Kept** (upstream has none). |
| `clipboard/clipboard_monitor_linux.py`, `clipboard/clipboard_manager.py` (backend choice) | `is_x_clipboard_owner()` used as a one-shot "is xclip usable?" probe at startup | **Fixed.** xclip answers "no owner for the CLIPBOARD selection" when the clipboard is empty, which is the normal state right after login, and that used to switch the client to `wl-paste` for the rest of the session. On GNOME/Mutter (no `wlr-data-control`) `wl-paste` reads need keyboard focus, so every poll stole focus from the active window (closed bookmark menus / extension popups, interrupted typing). Now "no owner" counts as usable, `--xmode` is recorded (`LINUX_XMODE_REQUESTED`) and never overridden, the auto-detected path retries the probe (`_XCLIP_PROBE_ATTEMPTS` × 1 s) because XWayland may still be starting, and `clipboard_manager` writes with xclip when `--xmode` was explicit. |

### Upstream changes that matter for this work (3.3.1 → 3.4.1)

Desktop client:

- **`utils/transport_manager.py` — `TransportManager(ReconnectMixin)`** (new): the single object
  `Application._get_ws_manager()` returns. `_connect_once()` calls
  **`utils/server_discovery.py`** (new) on *every* attempt, which re-fetches `/server-mode`,
  `/stun-url` or `/max-size` and rewrites `server_mode`/`stun_url`/`maxsize`/`websocket_url`.
  Only a `404` on `/server-mode` falls back to cached settings. Inner managers get
  `reconnect_handler = transport._start_reconnect`, so exactly one retry worker runs, and
  `ReconnectMixin._start_reconnect()` now delegates to that handler. Server switching
  (P2S ↔ P2P) waits for the old P2P `_disconnect_future`.
- **Per-platform tray rewrite**: `gui/linux_tray.py` (`LinuxTrayIcon`, keeps GTK/AppIndicator
  menus live while open), `gui/windows_tray.py`, `gui/macos_tray.py`, `gui/tk_owner.py`
  (one shared `_GuiRoot`; every window is now a `Toplevel` on it), `Menu` items keyed by
  `_clipcascade_key` so dynamic labels keep their identity.
- **`gui/login.py` rework**: clipboard-limit amount + unit combobox (`core/clipboard_limit.py`),
  download folder / CA bundle pickers, `login_form.cancelled` instead of an `on_quit_callback`
  that raised `SystemExit` inside Tk, success dialog with "don't show again"
  (`hide_login_success_dialog`), and `send_clipboard` / `receive_clipboard` preferences.
- **`core/config.py`**: new device preferences `download_notifications`,
  `clipboard_notifications`, `send_clipboard`, `receive_clipboard`,
  `hide_login_success_dialog`; still atomic tempfile + `os.replace` in `_save_data()`.
- **`utils/notification_manager.py`**: `notify(..., preference=...)`, bounded clipboard-received
  previews (`notify_clipboard_received`).
- **P2P hardening**: `P2P_CONNECTION_TIMEOUT_SEC` (90 s), `utils/aioice_compat.py`,
  stale open data-channel recovery (#189), fragment TTL, sleep/wake recovery.
- **Files**: `clipboard/file_utils.py` (downloads), `utils/main_thread.py`,
  `utils/window_manager.py`, `main.py` (`sys.exit(130)` on Ctrl+C).
- Still true from 3.3.x: `ReconnectMixin` jitter, STOMP client `Event` rewrite, update checker,
  lock-file rework, macOS AppKit loop.

Previous migration (3.2.0 → 3.3.1, for background):

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

Flow in `Application.run()` → `authenticate_and_connect()`. All connects go through
`TransportManager`, so every attempt starts with a `server_discovery` round-trip.

1. **Stored cookie** (only when usable: `not cipher_enabled or hashed_password is not None` —
   3.4.x's rule, without the key the payloads could not be decrypted) →
   `_connect_with_stored_session()`. On a failed connect it probes `GET /csrf-token`:
   - `200` → session valid, so the failure is transient (DNS, Wi-Fi, proxy) → sleep with
     `STARTUP_RECONNECT_INITIAL_DELAY` (2 s) doubling to `STARTUP_RECONNECT_MAX_DELAY` (30 s),
     retry forever. One notification after `STARTUP_RECONNECT_NOTIFY_AFTER` (20 s).
   - `3xx` (redirect to login), `401`, `403` → session rejected → stop retrying.
   - network error → unknown → keep retrying (same as `200`).
2. **Saved credentials** (`save_password` and encryption disabled) → `_apply_login()` silently.
3. **Interactive** login form (`_login_interactively()`), looping until success. Closing the
   window sets `login_form.cancelled`; the process then exits from outside Tk. The success
   dialog is shown here (not for the silent paths) and honours
   `hide_login_success_dialog` + "don't show again".

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
there. It sets `hashed_password` *before* connecting, because connecting installs the clipboard
listeners and they need the key immediately.

Note that `_refresh_session()` runs on the retry worker and calls `connect()` itself after a
successful re-login; the worker then calls `connect()` again, which is an idempotent no-op once
the manager is connected.

---

## 5. Linux specifics worth remembering

- **Tray**: `pystray` needs PyGObject (`gi`) for its AppIndicator backend. 3.4.x selects
  `gui/linux_tray.LinuxTrayIcon` only when `Icon.__module__` is `pystray._gtk` or
  `pystray._appindicator`; otherwise it silently uses its legacy X11 backend, whose icon cannot
  open a menu at all (`pystray._xorg.Icon.HAS_MENU is False`). The client logs an error naming
  the backend; `clipcascade.service` and the README document the Fedora build deps and
  `uv sync --extra tray`. Verify with `python -c "import pystray; print(pystray.Icon)"` →
  `pystray._appindicator.Icon`.
- **Wayland clipboard**: the Wayland monitor also imports `gi`; without it the client logs
  `Failed to start clipboard monitor` and polls XWayland (`--xmode true`).
- **Clipboard backend**: an XWayland session gets xclip, which reads and writes the Wayland
  clipboard through Mutter's X11 bridge (verified: `xclip -o` returns a clipboard owned by
  `wl-copy`). Native Wayland gets `wl-paste --watch` when the compositor implements
  `wlr-data-control` (wlroots, KDE), otherwise wl-paste polling — and on GNOME/Mutter that
  polling needs keyboard focus, so it steals focus from the active window every poll. Never
  treat an empty clipboard as "xclip is broken"; `--xmode true` forces xclip and is what a
  GNOME/Wayland systemd unit should pass (the log then says `Clipboard backend: xclip`).
- **Fonts**: Tk silently falls back to the bitmap `fixed` font for unknown families. Always use
  `utils/fonts.ui_font(size, [weight=], [underline=], master=<widget or root>)` for new Tk UI
  text — never `("Helvetica", n)` / `("Arial", n)`. Pixel sizes (negative) cannot be validated
  by comparing the reported size; only point sizes are compared. Since 3.4.0 there is exactly one
  Tcl interpreter (`gui/tk_owner.py`), so `master=` any widget of the window being built; the
  resolved fonts are cached on that shared root. ttk style names (`TLabel`, `Dialog.TLabel`) are
  global, so a dialog that reconfigures one changes it for every window.
- **Startup ordering**: `graphical-session.target` is reached before networking, hence the
  startup retry. The systemd unit deliberately has no `After=network-online.target`; the client
  copes on its own.
- **Runtime artifacts** in `ClipCascade_Desktop/src/` when running from source: `DATA`
  (`0600`), `clipcascade_log.log`, `clipcascade.lock`, `uv.lock` — all git-ignored. Don't
  `git add -A` that directory (this happened once during the migration and put an empty
  `clipcascade.lock` into a commit).

---

## 6. Working with upstream

- `git fetch upstream && git log --oneline main..upstream/main` to see new upstream work; local
  `main` is a fast-forward of `upstream/main` and is pushed to `origin/main`.
- Rebase with `git rebase --onto upstream/main <old-base> fix/desktop-autologin-reliability`, or
  `git rebase upstream/main` while checked out.
- **Conflict hot spots** (expect all five on a large upstream change):
  1. `core/application.py` — upstream keeps editing `authenticate_and_connect()`, `run()` and now
     `TransportManager` wiring. Re-resolve by *reading the new flow*, not by replaying the diff.
  2. `gui/login.py` — upstream reworks labels/tooltips/layout; re-apply `ui_font(...)` to any new
     `font=` argument (a regex over `("Helvetica", n)` / `("Arial", n[, "bold"])` is fastest).
  3. `gui/info.py` — upstream renamed the ttk styles (`TLabel` → `Dialog.TLabel`); the font patch
     has to follow the new names and the new `on_dont_show_again` parameter.
  4. `README.md` — upstream rewrites the Linux install, reverse-proxy and advanced-settings
     sections; re-anchor the uv/systemd/tray/log sections by heading, not by line.
  5. `pyproject.toml` / `requirements_linux_gui.txt` — keep upstream pins, add the `tray` extra and
     `PyGObject` line after them.
- Before rebasing, create a safety ref: `git branch backup/<name> HEAD` and, if the branch is
  published, push it. The branch is force-pushed after a rebase (`--force-with-lease` is
  preferred).
- Commit messages follow the PR-title grammar even for single commits; each commit is atomic and
  should stay buildable.

### Upstream PR plan

The local commits are **five independent fixes** plus two fork-only doc commits. Do not open one giant PR: each item below is
a self-contained change that upstream can review and release on its own (the user explicitly
wants separate PRs). Two commits are fork-only (`AGENTS.md`) and must never be included.

| # | PR title (= commit subject, PR-title grammar) | Commits to cherry-pick | Notes |
|---|---|---|---|
| 1 | `fix(linux-gui): keep the session across restarts and slow networks` | `keep the session across restarts…` | Release-relevant. Touches `core/application.py`, `core/config.py`, `core/constants.py`, `utils/reconnect.py`, `utils/request_manager.py`. Explain in the body that 3.4.0's `TransportManager` owns the retry worker, so the re-auth hook lives on `ReconnectMixin` (`_before_reconnect`), **not** on `interfaces/ws_interface.py` — reviewers will look for the old interface addition otherwise. |
| 2 | `fix(linux-gui): keep the xclip backend when the clipboard is empty` | `keep the xclip backend when the clipboard is empty` + `docs: document the GNOME Wayland clipboard fallback` | Independent of everything else. Touches `clipboard/clipboard_monitor_linux.py`, `clipboard/clipboard_manager.py`, `core/constants.py` (`LINUX_XMODE_REQUESTED`), README + contrib unit. Body: an empty clipboard at login is normal and used to look like "xclip is broken"; the wl-paste fallback needs keyboard focus on Mutter and closed bookmark menus / extension popups. |
| 3 | `fix(linux-gui): resolve UI fonts at runtime and report a tray without a menu` | `resolve UI fonts at runtime…`, `honour pixel-sized UI fonts`, `warn when the tray falls back to the X11 backend` | Can be split again into "fonts" and "tray warning" if upstream prefers; both are tiny. Touches `utils/fonts.py` (new), `gui/login.py`, `gui/info.py`, `gui/tray.py`. |
| 4 | `fix(linux-gui): keep log history instead of truncating it on every start` | `keep log history…` | Smallest fix; `RotatingFileHandler` 5 MiB × 2, `LOG_FILE_*` constants. |
| 5 | `docs: document a uv install and a systemd user unit for the Linux client` | `docs: add a systemd user unit…`, `docs: document a uv-native install…`, `chore: ignore local lock files…` | Non-releasing (`docs:`/`chore:` **must not** have a scope), so it will not trigger a release. Carries the shared-metadata edits (`requires-python >=3.9`, `tray` extra, `PyGObject` line) — decide explicitly whether those belong in this PR or in their own `build:`/`chore:` one. |
| — | *(never)* | `docs: record the fork's divergence…`, `docs: update the fork notes…` | Fork-only; `AGENTS.md` must stay out of every PR. |

Mechanics:

```bash
git fetch upstream
git switch -c fix/xclip-backend upstream/main
git cherry-pick <sha> <sha>            # use the subjects above; SHAs change on every rebase
git push origin fix/xclip-backend
```

- Open PRs against `upstream/main` one at a time. PRs 1, 2 and 3 all touch
  `core/constants.py` and PRs 1/5 both touch `README.md`, so whichever merges first makes the
  others need a rebase — that is expected, rebase locally and force-push the PR branch.
- Each PR **Description** becomes the GitHub release notes: user-facing bullets, no
  implementation detail, and the scopes must list every changed platform. Per-PR bullets:
  - **PR 1:** no login form while the network is still coming up; sessions are refreshed
    automatically when a password is stored; the stored session is only re-used while its
    encryption key is present; REST calls and the stored `DATA` file are safer (timeouts,
    `0600`).
  - **PR 2:** the tray no longer loses keyboard focus every few seconds on GNOME/Wayland
    (clipboard polling no longer pulls focus); an explicit `--xmode` is always respected.
  - **PR 3:** the tray icon reports when PyGObject is missing (it had no menu at all in that
    case); UI text no longer shrinks to an unreadable bitmap font on Tk builds without Xft.
  - **PR 4:** logs are kept across restarts (rotated, 5 MiB × 2) instead of being truncated.
  - **PR 5:** a `uv` install path and a systemd user unit are documented.
- Checklist per PR: correct title grammar/scope, description filled in, tested locally on
  Linux (GUI **and** CLI), no `AGENTS.md`, no `DATA`/logs/locks/`uv.lock`, no secrets.
- Decide explicitly whether `requires-python >=3.9` and the `tray` extra belong in PR 5; they
  are packaging fixes needed for the documented `uv` flow, but they touch shared metadata.
  Note that upstream's own code uses `list | None` annotations, which need Python 3.10 at
  runtime even though the metadata still says `>=3.8` — don't try to "fix" that here.

---

## 7. Verification (no upstream desktop test suite)

Environment used for the 2026-11-03 migration: `ClipCascade_Desktop/src/.venv`
(Python 3.12.13), managed with `uv` and now refreshed to 3.4.1's dependency set
(`uv sync --extra tray` pulled `prompt-toolkit`, `pyfiglet`, Pillow 12, PyGObject 3.58.1…).
`python3` on the host is 3.14 and has none of the deps. `gi`/PyGObject and
`pystray._appindicator.Icon` are present, and a display is available (`DISPLAY=:0`;
`xrandr` is missing, which only produces a harmless monitor-size warning). The desktop is
**GNOME 51 on Wayland/Mutter** (`XDG_SESSION_TYPE=wayland`, `DISPLAY=:0`, so
`detect_linux_display_server()` says `XWayland` and `XMODE` defaults to `True`), with the
`clipboard-indicator` and `appindicatorsupport` extensions enabled — that is the exact setup
the xclip backend exists for.

Static:

```bash
cd ClipCascade_Desktop/src
.venv/bin/python -m compileall -q -x '\.venv' .
.venv/bin/python -c "import core.application; print('ok')"   # imports the GUI path + p2p/aiortc
.venv/bin/python -c "import cli.login, cli.tray; print('ok')"  # Linux CLI needs pyfiglet/prompt_toolkit
.venv/bin/python -c "import utils.reconnect, utils.fonts, utils.request_manager, utils.transport_manager; print('ok')"
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
  no-op without a callback, runs exactly once per retry attempt; `TransportManager` inherits the
  mixin and therefore exposes `set_relogin_callback()` (the interface patch is gone).
- `authenticate_and_connect()`: a plain cookie tries the stored session; an encrypted cookie
  *with* `hashed_password` does too; an encrypted cookie *without* the key skips it and goes
  straight to the login form (3.4.x's usability rule).
- GUI (real display): `ui_font(13)` resolves to `liberation sans` (tk scaling 2.67, the exact
  192 DPI/no-Xft scenario the font fix targets); `LoginForm` and `CustomDialog` construct; every
  ttk style they configure (`TLabel`, `TEntry`, `TButton`, `Path.TButton`, `TCheckbutton`,
  `Dialog.TLabel`, `Header.Dialog.TLabel`, `Dialog.TButton`, `Dialog.TCheckbutton`), the title
  label, the `HoverTooltip` label and the dialog's `ScrolledText` all resolve to that family,
  i.e. none fall back to the bitmap `fixed` font.
- Tray warning: a stub icon with `HAS_MENU = False` (module `pystray._xorg`) logs the error
  naming `_xorg`; an icon with `HAS_MENU = True` logs nothing.
- Clipboard backend selection (stub `execute_command`/`_xclip_is_available`, no display
  needed): `TARGETS` readable → `True`; `"no owner for the CLIPBOARD selection"` → still
  `True` (empty clipboard is not a broken X connection); `"Can't open display"` → `False`;
  missing `xclip` (`FileNotFoundError`) → `False` without raising. Backend matrix:
  auto-XWayland + empty clipboard → xclip; auto-XWayland + broken xclip → wl-paste (after the
  `_XCLIP_PROBE_ATTEMPTS` × 1 s retries); `--xmode true` + broken xclip → still xclip;
  `XMODE` off → `wl-paste --watch`, then polling when watch exits.
- `--xmode` parsing (`python -c "import core.constants as c; …" --xmode …`): bare `--xmode`
  exits 2 with `--xmode requires true or false`; `--xmode true` sets `XMODE=True` and
  `LINUX_XMODE_REQUESTED=True`; `--xmode true --gui true` keeps `LINUX_USE_CLI_UI=False`.
- Live on the GNOME/Mutter session (real clipboard): `wl-copy --clear`, start
  `_start_clipboard_polling()` with `XMODE=True`, then `wl-copy` text → the monitor reports it
  and no `wl-paste` process exists; `ClipboardManager.paste("…", "text")` writes through xclip
  and `wl-paste -n` reads it back (Mutter's X11↔Wayland bridge in both directions). The
  service must log `Clipboard backend: xclip` and never `Switching to wl-clipboard`.
- End-to-end with a copied source tree and a `DATA` cookie pointing at a dead port: log shows
  `retrying in 2s` → `4s` → `8s`, no login form, no crash — in GUI *and* CLI mode. Every retry
  now starts with `server_discovery`, so a refused `/server-mode` is the first log line of each
  attempt. A 302 stub makes the client log "The server rejected the stored session; a new login
  is required" and open the login form once (no retry loop).
- Log rotation: two consecutive runs both appear in `clipcascade_log.log`; `DATA` ends up `0600`.

Not verified live (needs a real ClipCascade server): STOMP/P2P reconnect after a server or
reverse-proxy restart, the silent re-auth on a genuine session expiry, and the P2S ↔ P2P
switch inside `TransportManager._connect_once()`. The hook, probe and
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
`ClipCascade_Server/reverse-proxy/README.md`, `.github/workflows/README.md` (release pipeline),
`.github/pull_request_template.md`.

```bash
# See what upstream added since the last migration (the fork has an `upstream` remote)
git fetch upstream && git log --oneline main..upstream/main
```
