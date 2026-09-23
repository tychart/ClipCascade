import logging
import sys
import time
from logging.handlers import RotatingFileHandler


from core.constants import *

from core.config import Config
from utils.request_manager import RequestManager
from utils.cipher_manager import CipherManager
from utils.notification_manager import NotificationManager
from stomp_ws.stomp_manager import STOMPManager
from p2p.p2p_manager import P2PManager

if PLATFORM == WINDOWS:
    import ctypes
elif PLATFORM == MACOS or PLATFORM.startswith(LINUX):
    import fcntl


if PLATFORM.startswith(LINUX) and LINUX_USE_CLI_UI:
    import pyfiglet
    from cli.login import LoginForm
    from cli.info import CustomDialog
    from cli.tray import TaskbarPanel
    from cli.message_box import MessageBox
    from cli.echo import Echo
else:
    from gui.login import LoginForm
    from gui.info import CustomDialog
    from gui.tray import TaskbarPanel
    from gui.message_box import MessageBox


class _WebsocketClientNoiseFilter(logging.Filter):
    """Drop websocket-client's "<error> - goodbye" line.

    The library logs it at ERROR for every failed connection attempt while the
    reconnect logic reports the same cause itself, so it would otherwise flood
    the log (and hide real errors) during an outage.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return "- goodbye" not in record.getMessage()


class Application:
    def __init__(
        self,
        log_file_path=LOG_FILE_NAME,
        data_file_path=DATA_FILE_NAME,
        mutex_identifier=MUTEX_NAME,
    ):
        try:
            self.log_file_path = os.path.join(
                get_program_files_directory(), log_file_path
            )
            self.data_file_path = os.path.join(
                get_program_files_directory(), data_file_path
            )
            self.mutex_identifier = mutex_identifier

            if PLATFORM == MACOS or PLATFORM.startswith(LINUX):
                self.lock_file = None  # File(lock) object
                self.mutex_identifier = os.path.join(
                    get_program_files_directory(), self.mutex_identifier
                )

            self.config = Config(
                file_name=self.data_file_path
            )  # Maintain a single configuration instance for the entire application lifecycle.

            self.request_manager = RequestManager(self.config)
            self.stomp_manager = STOMPManager(self.config)
            self.p2p_manager = P2PManager(self.config)
            self.cipher_manager = CipherManager(self.config)
            self.notification_manager = NotificationManager(self.config)
            # Timestamp of the last session validity probe (used to throttle it).
            self._last_session_probe = 0.0
            # Avoid repeating the "log in again" notification on every probe.
            self._relogin_notified = False
        except Exception as e:
            CustomDialog(
                f"An error occurred during application initialization: {e}",
                msg_type="error",
            ).mainloop()

    def setup_logging(self):
        LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
        if LOG_FILE_MAX_BYTES > 0:
            # Keep the log across restarts (and cap its size) instead of
            # truncating it on every start, so failures can still be inspected
            # afterwards.
            handler = RotatingFileHandler(
                self.log_file_path,
                maxBytes=LOG_FILE_MAX_BYTES,
                backupCount=LOG_FILE_BACKUP_COUNT,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter(LOG_FORMAT))
            logging.basicConfig(level=LOG_LEVEL, handlers=[handler])
        else:
            logging.basicConfig(
                level=LOG_LEVEL,
                format=LOG_FORMAT,
                filename=self.log_file_path,
                filemode="a",
                encoding="utf-8",
            )
        logging.getLogger("websocket").addFilter(_WebsocketClientNoiseFilter())

    def ensure_single_instance(self):
        if PLATFORM == WINDOWS:
            ctypes.windll.kernel32.CreateMutexW(None, False, self.mutex_identifier)
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                CustomDialog(
                    "Another instance of ClipCascade is already running.",
                    msg_type="warning",
                ).mainloop()
                sys.exit(0)
        elif PLATFORM == MACOS or PLATFORM.startswith(LINUX):
            if PLATFORM == MACOS:
                app_dir = get_program_files_directory()
                if not os.path.exists(app_dir):
                    try:
                        os.makedirs(app_dir)
                    except Exception as e:
                        CustomDialog(
                            f"An error occurred while creating the directory '{app_dir}'. Error: {e}",
                            msg_type="error",
                        ).mainloop()
                        sys.exit(1)

            # Create the lock file
            try:
                self.create_lock_file()
            except IOError:
                run_anyway = MessageBox().askquestion(
                    "ClipCascade",
                    "Another instance of ClipCascade is already running. Do you want to run anyway?",
                )
                if run_anyway == "yes":
                    os.remove(self.mutex_identifier)
                    self.create_lock_file()
                else:
                    self.lock_file = None
                    sys.exit(0)

    def create_lock_file(self, path=None):
        if path is None:
            path = self.mutex_identifier

        if PLATFORM == MACOS or PLATFORM.startswith(LINUX):
            self.lock_file = open(path, "w")
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _has_saved_credentials(self) -> bool:
        """True when we can log in again without asking the user.

        The stored value is the SHA3-512 hash the server expects, never the
        password itself. When encryption is enabled the derived key must be
        available too, because it cannot be derived from the hash.
        """
        if not (
            self.config.data.get("save_password")
            and self.config.data.get("username")
            and self.config.data.get("password")
        ):
            return False
        if self.config.data.get("cipher_enabled") and not self.config.data.get(
            "hashed_password"
        ):
            return False
        return True

    def _apply_login(self) -> tuple[bool, str]:
        """Log in with the current credentials and open the WebSocket.

        Expects ``config.data["password"]`` to hold the SHA3-512 hash of the
        password (the value the server compares against).
        """
        login_successful, msg_login, cookie = self.request_manager.login()
        if not login_successful:
            return False, "Login Failed\n" + msg_login

        self.config.data["cookie"] = cookie
        self.config.data["csrf_token"] = self.request_manager.get_csrf_token()
        self.config.data["server_mode"] = self.request_manager.get_server_mode()
        if self.config.data["server_mode"] == "P2P":
            self.config.data["stun_url"] = self.request_manager.get_stun_url()
            self.config.data["maxsize"] = -1
            self.config.data["websocket_url"] = Config.convert_to_websocket_url(
                self.config.data["server_url"], WEBSOCKET_ENDPOINT_P2P
            )
        else:
            self.config.data["stun_url"] = ""
            self.config.data["maxsize"] = self.request_manager.maxsize()
            self.config.data["websocket_url"] = Config.convert_to_websocket_url(
                self.config.data["server_url"], WEBSOCKET_ENDPOINT
            )

        ws_conn_successful, msg = self._get_ws_manager().connect()
        if not ws_conn_successful:
            return False, (
                "Login successful but websocket connection failed. \n"
                "Please check websocket-url\n" + msg
            )

        self._get_ws_manager().is_login_phase = False
        # Persist the fresh cookie (and the credentials, if the user opted in)
        # so the next start can connect without asking for a password.
        self.config.save()
        return True, ""

    def _connect_with_stored_session(self) -> bool:
        """Connect using the stored session cookie.

        A transient failure here (no DNS yet, Wi-Fi still associating, server
        briefly down) must not send the user back to the login form, so keep
        retrying while the server is merely unreachable. Only give up when the
        server itself rejects the session.
        """
        ws_manager = self._get_ws_manager()
        delay = STARTUP_RECONNECT_INITIAL_DELAY
        attempt = 0
        started_at = time.monotonic()
        notified = False

        while True:
            attempt += 1
            connected, msg = ws_manager.connect()
            if connected:
                ws_manager.is_login_phase = False
                if attempt > 1:
                    logging.info(
                        f"WebSocket connected after {attempt} attempt(s) "
                        f"({time.monotonic() - started_at:.1f}s)"
                    )
                return True

            if self.request_manager.session_is_valid() is False:
                logging.warning(
                    "The server rejected the stored session; a new login is required"
                )
                return False

            if not notified and (
                time.monotonic() - started_at >= STARTUP_RECONNECT_NOTIFY_AFTER
            ):
                self.notification_manager.notify(
                    title=f"{APP_NAME}: Waiting for server…",
                    message=(
                        "The server is not reachable yet. ClipCascade will connect "
                        "automatically once it is."
                    ),
                )
                notified = True

            logging.warning(f"{msg} - retrying in {delay}s")
            time.sleep(delay)
            delay = min(
                delay * STARTUP_RECONNECT_BACKOFF_FACTOR, STARTUP_RECONNECT_MAX_DELAY
            )

    def _login_interactively(self):
        """Ask the user for credentials until the login succeeds."""
        if PLATFORM.startswith(LINUX) and LINUX_USE_CLI_UI:
            Echo("═" * 14 + "\n║ LOGIN FORM ║\n" + "═" * 14)

        while True:
            self.config.data["password"] = ""  # Clear the password
            login_form = LoginForm(
                self.config,
                on_quit_callback=(
                    None
                    if (PLATFORM.startswith(LINUX) and LINUX_USE_CLI_UI)
                    else lambda: sys.exit(0)
                ),
            )
            login_form.mainloop()  # wait until login form is closed
            # Keep the raw password around: it is needed to derive the
            # encryption key, which cannot be derived from the password hash.
            raw_password = self.config.data["password"]
            self.config.data["password"] = (
                CipherManager.string_to_sha3_512_lowercase_hex(raw_password)
            )

            login_successful, msg = self._apply_login()
            if login_successful:
                if self.config.data["cipher_enabled"]:
                    self.config.data["hashed_password"] = (
                        self.cipher_manager.hash_password(raw_password)
                    )
                if not self.config.data["save_password"]:
                    self.config.data["password"] = ""
                self.config.save()
                CustomDialog(
                    "Success! ClipCascade will now run in the task bar/menu bar.",
                    msg_type="success",
                    timeout=5000,
                ).mainloop()
                return

            raw_password = None  # Clear the raw password
            CustomDialog(msg, msg_type="error").mainloop()
            if PLATFORM.startswith(LINUX) and LINUX_USE_CLI_UI:
                Echo("-" * 53)

    def _refresh_session(self) -> bool:
        """Re-authenticate when the server invalidated the stored session.

        Called before every automatic reconnect attempt, so it may run on the
        WebSocket thread: it never opens a UI. Returns True when the session is
        (or may still be) valid.
        """
        try:
            if not self.config.data.get("cookie"):
                return False

            now = time.monotonic()
            if now - self._last_session_probe < SESSION_PROBE_MIN_INTERVAL:
                return True
            self._last_session_probe = now

            if (
                self.request_manager.session_is_valid(timeout=SESSION_PROBE_TIMEOUT)
                is not False
            ):
                # Valid, or the server is unreachable: let the normal reconnect
                # loop keep trying.
                self._relogin_notified = False
                return True

            if not self._has_saved_credentials():
                if not self._relogin_notified:
                    logging.warning(
                        "The server rejected the stored session and no credentials "
                        "are saved. Log in again from the ClipCascade tray menu "
                        "(Logoff and Quit, then start ClipCascade)."
                    )
                    self.notification_manager.notify(
                        title=f"{APP_NAME}: Log in again",
                        message=(
                            "The server session expired. Use 'Logoff and Quit' in the "
                            "tray menu, then start ClipCascade to log in again."
                        ),
                    )
                    # Do not repeat this on every reconnect attempt.
                    self._relogin_notified = True
                return False

            logging.info(
                "The server rejected the stored session; re-authenticating with the "
                "saved credentials"
            )
            login_successful, msg = self._apply_login()
            if login_successful:
                return True
            logging.error(f"Automatic re-authentication failed: {msg}")
            return False
        except Exception as e:
            logging.error(f"Error while refreshing the session: {e}")
            return False

    def authenticate_and_connect(self):
        # 1. Try the stored session cookie. Transient failures are retried, so a
        #    slow network at startup does not force the user to log in again.
        if self.config.data.get("cookie"):
            if self._connect_with_stored_session():
                return

        # 2. The cookie is missing, or the server rejected it. Log in again
        #    without bothering the user when credentials were saved.
        if self._has_saved_credentials():
            logging.info("Logging in with the saved credentials")
            login_successful, msg = self._apply_login()
            if login_successful:
                return
            logging.warning(f"Saved credentials were rejected: {msg}")

        # 3. Fall back to asking the user.
        self._login_interactively()

    def _get_ws_manager(self):
        if self.config.data["server_mode"] == "P2P":
            return self.p2p_manager
        else:
            return self.stomp_manager

    def get_version_update_status(self) -> list:
        """
        Checks for a new version of the application by comparing the current version
        with the one available in a remote JSON file.

        Returns:
        list: [bool, str, str, str] - [Is new version available, latest version, current version, release URL]
        """
        try:
            response = RequestManager.get(VERSION_URL)
            response_data = response.json()
            if PLATFORM == WINDOWS:
                key = "windows"
            elif PLATFORM == MACOS:
                key = "macos"
            elif PLATFORM.startswith(LINUX):
                if not LINUX_USE_CLI_UI:
                    key = "linux_gui"
                else:
                    key = "linux_non_gui"

            if response_data[key] != APP_VERSION:
                return [True, response_data[key], APP_VERSION, RELEASE_URL]
        except Exception as e:
            logging.error(f"Error checking for new version: {e}")
        return [False, "", APP_VERSION, RELEASE_URL]

    def get_donation_url(self) -> str:
        try:
            metadata = self.request_manager.get_metadata()
            if metadata is not None:
                return metadata.get("funding", None)
        except Exception as e:
            logging.error(f"Error fetching metadata: {e}")
        return None

    def logoff_and_exit(self):
        try:
            self._get_ws_manager().disconnect()
            self.request_manager.logout()
            self.config.data["hashed_password"] = None
            self.config.data["cookie"] = None
            self.config.data["maxsize"] = None
            self.config.data["password"] = ""
            self.config.data["csrf_token"] = ""
            self.config.save()
        except Exception as e:
            raise Exception(f"Error during logging off: {e}")

    def banner(self):
        if PLATFORM.startswith(LINUX) and LINUX_USE_CLI_UI:
            Echo(pyfiglet.figlet_format(APP_NAME))
            Echo("*" * 53)
            Echo("Real-Time Clipboard Syncing".center(53))
            Echo(GITHUB_URL.center(53))
            Echo("*" * 53)

    def run(self):
        try:
            self.banner()
            self.setup_logging()
            self.ensure_single_instance()
            self.config.load()
            # Let the transport re-authenticate itself when the server
            # invalidates our session (e.g. after a server/proxy restart).
            self._get_ws_manager().set_relogin_callback(self._refresh_session)
            self.authenticate_and_connect()
            self.config.save()
            update_available = self.get_version_update_status()
            donation_url = self.get_donation_url()

            sys_tray = TaskbarPanel(
                on_connect_callback=self._get_ws_manager().manual_reconnect,
                on_disconnect_callback=self._get_ws_manager().disconnect,
                on_logoff_callback=self.logoff_and_exit,
                new_version_available=update_available,
                github_url=GITHUB_URL,
                donation_url=donation_url,
                ws_interface=self._get_ws_manager(),
                config=self.config,
            )
            self._get_ws_manager().set_tray_ref(sys_tray)
            sys_tray.run()
        except Exception as e:
            msg = f"An unexpected error has occurred: {e}"
            logging.error(msg)
            CustomDialog(
                msg + "\nCheck logs in project directory", msg_type="error"
            ).mainloop()
        finally:
            self._get_ws_manager().disconnect()
            if PLATFORM == MACOS or PLATFORM.startswith(LINUX):
                if self.lock_file is not None:
                    fcntl.flock(self.lock_file, fcntl.LOCK_UN)
                    self.lock_file.close()
                    os.remove(self.mutex_identifier)
