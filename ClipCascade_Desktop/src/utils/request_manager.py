import json
import logging
from typing import Optional

import requests
from core.constants import *
from core.config import Config
from bs4 import BeautifulSoup
from utils.ssl_helper import requests_verify_arg


class RequestManager:
    def __init__(self, config: Config):
        self.config = config

    def _verify(self):
        return requests_verify_arg(self.config)

    @staticmethod
    def format_cookie(cookie: dict) -> str:
        """
        Format the cookie string for headers.
        """
        return f"JSESSIONID={cookie.get('JSESSIONID', '')};"

    def login(self) -> tuple[bool, str, dict]:
        try:
            session = requests.Session()

            # Fetch the login page to get the CSRF token
            response = session.get(
                self.config.data["server_url"] + LOGIN_URL,
                verify=self._verify(),
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                msg = f"Failed to fetch login page: {response.status_code}"
                logging.error(msg)
                return False, msg, None

            soup = BeautifulSoup(response.text, "html.parser")
            csrf_token = soup.find("input", {"name": "_csrf"})["value"]

            # Login with the credentials
            form_data = {
                "username": self.config.data["username"],
                "password": self.config.data["password"],
                "_csrf": csrf_token,
            }
            response = session.post(
                self.config.data["server_url"] + LOGIN_URL,
                data=form_data,
                verify=self._verify(),
                timeout=REQUEST_TIMEOUT,
            )
            if (
                response.status_code == 200
                and "bad credentials" not in response.text.lower()
            ):
                # login successful
                cookie = session.cookies.get_dict()
                logging.info(f"Login successful: {response.status_code}")
                return True, "Login successful", cookie
            else:
                # login failed
                msg = f"Login failed: {response.status_code}"
                logging.error(msg)
                return False, msg, None
        except Exception as e:
            msg = f"An error occurred during login: {e}"
            logging.error(msg)
            return False, msg, None

    def session_is_valid(self, timeout: int = REQUEST_TIMEOUT) -> Optional[bool]:
        """
        Ask the server whether the stored session cookie is still accepted.

        This distinguishes "the server rejected our session" (the user has to
        authenticate again) from "the server is unreachable" (keep retrying),
        which the WebSocket layer alone cannot tell apart.

        Returns:
            True  - the server accepts the session.
            False - the server rejected it (redirect to the login page, 401 or 403).
            None  - the server could not be reached; validity is unknown.
        """
        if not self.config.data.get("cookie"):
            return False

        url = self.config.data["server_url"] + CSRF_URL
        try:
            response = requests.get(
                url,
                headers={
                    "Cookie": RequestManager.format_cookie(self.config.data["cookie"])
                },
                verify=self._verify(),
                timeout=timeout,
                # Do not follow the redirect to the login page: the redirect
                # itself is the signal that the session is no longer valid.
                allow_redirects=False,
            )
        except requests.RequestException as e:
            # Normal while retrying at startup: the caller reports the retry.
            logging.debug(f"Could not verify the session with {url}: {e}")
            return None

        if response.status_code == 200:
            return True
        if response.status_code in (401, 403) or 300 <= response.status_code < 400:
            return False
        logging.warning(
            f"Unexpected response while verifying the session: {response.status_code}"
        )
        return None

    def maxsize(self) -> int:
        try:
            response = RequestManager.get(
                url=self.config.data["server_url"] + MAXSIZE_URL,
                headers={
                    "Cookie": RequestManager.format_cookie(self.config.data["cookie"])
                },
                verify=self._verify(),
            )
            if response.status_code == 200:
                # maxsize request successful
                maxsize = response.json().get("maxsize", MAX_SIZE)
                logging.info(f"Max size: {maxsize}")
                return maxsize
        except Exception as e:
            logging.error(
                f"Error fetching max size: {e}, defaulting to {MAX_SIZE} Bytes"
            )
        return MAX_SIZE

    def get_server_mode(self) -> str:
        try:
            response = RequestManager.get(
                url=self.config.data["server_url"] + SERVER_MODE_URL,
                headers={
                    "Cookie": RequestManager.format_cookie(self.config.data["cookie"])
                },
                verify=self._verify(),
            )
            if response.status_code == 200:
                # server mode request successful
                server_mode = response.json().get("mode")
                logging.info(f"Server mode: {server_mode}")
                return server_mode
        except Exception as e:
            logging.error(f"Error fetching server mode: {e}")
            raise

    def get_stun_url(self) -> str:
        try:
            response = RequestManager.get(
                url=self.config.data["server_url"] + STUN_URL,
                headers={
                    "Cookie": RequestManager.format_cookie(self.config.data["cookie"])
                },
                verify=self._verify(),
            )
            if response.status_code == 200:
                # stun url request successful
                stun_url = response.json().get("url")
                logging.info(f"STUN URL: {stun_url}")
                return stun_url
        except Exception as e:
            logging.error(f"Error fetching STUN URL: {e}")
            raise

    def get_metadata(self) -> dict:
        try:
            response = RequestManager.get(
                url=METADATA_URL,
                headers={
                    "Cookie": RequestManager.format_cookie(self.config.data["cookie"])
                },
                verify=True,
            )
            if response.status_code == 200:
                # metadata request successful
                return response.json()
        except Exception as e:
            logging.error(f"Error fetching metadata: {e}")
            raise

    def logout(self):
        try:
            response = RequestManager.post(
                url=self.config.data["server_url"] + LOGOUT_URL,
                data={"_csrf": self.config.data["csrf_token"]},
                headers={
                    "Cookie": RequestManager.format_cookie(self.config.data["cookie"])
                },
                verify=self._verify(),
            )
            if response.status_code == 204:
                logging.info(f"Logout successful: {response.status_code}")
        except Exception as e:
            logging.error(f"Error during logout: {e}")

    def get_csrf_token(self) -> str:
        try:
            response = RequestManager.get(
                url=self.config.data["server_url"] + CSRF_URL,
                headers={
                    "Cookie": RequestManager.format_cookie(self.config.data["cookie"])
                },
                verify=self._verify(),
            )

            if response.status_code == 200:
                # CSRF token request successful
                return json.loads(response.text).get("token", "")
        except Exception as e:
            logging.error(f"Error fetching CSRF token: {e}")
            return ""

    @staticmethod
    def get(
        url: str,
        headers: dict = None,
        verify=True,
        timeout: int = REQUEST_TIMEOUT,
    ) -> requests.Response:
        """
        A generic GET mapper for handling GET requests.
        """
        try:
            response = requests.get(
                url, headers=headers, verify=verify, timeout=timeout
            )
            response.raise_for_status()  # Will raise an HTTPError if the HTTP request returned an unsuccessful status code
            return response
        except Exception as e:
            logging.error(f"Error during GET request to {url}: {e}")
            raise

    @staticmethod
    def post(
        url: str,
        data: dict,
        headers: dict = None,
        verify=True,
        timeout: int = REQUEST_TIMEOUT,
    ) -> requests.Response:
        """
        A generic POST mapper for handling POST requests.
        """
        try:
            response = requests.post(
                url, data=data, headers=headers, verify=verify, timeout=timeout
            )
            response.raise_for_status()  # Will raise an HTTPError if the HTTP request returned an unsuccessful status code
            return response
        except Exception as e:
            logging.error(f"Error during POST request to {url}: {e}")
            raise
