from abc import ABC, abstractmethod

from cli.tray import TaskbarPanel
from core.config import Config


class WSInterface(ABC):
    ############################
    #    ABSTRACT VARIABLES    #
    ############################
    is_auto_reconnecting: bool = False

    # Optional callable set by the application; invoked before every automatic
    # reconnect attempt so the session can be refreshed before retrying.
    relogin_callback = None

    def set_relogin_callback(self, callback):
        """Register a callable invoked before every automatic reconnect attempt.

        The application uses this to re-authenticate when the server has
        invalidated the stored session (for example after a server or reverse
        proxy restart), so the connection recovers without user interaction.
        """
        self.relogin_callback = callback

    @abstractmethod
    def __init__(self, config: Config, is_login_phase=True):
        """This method must be implemented in subclasses."""
        pass

    @abstractmethod
    def get_total_timeout(self):
        """This method must be implemented in subclasses."""
        pass

    @abstractmethod
    def get_stats(self):
        """This method must be implemented in subclasses."""
        pass

    @abstractmethod
    def connect(self):
        """This method must be implemented in subclasses."""
        pass

    @abstractmethod
    def set_tray_ref(self, sys_tray: TaskbarPanel):
        """This method must be implemented in subclasses."""
        pass

    @abstractmethod
    def manual_reconnect(self):
        """This method must be implemented in subclasses."""
        pass

    @abstractmethod
    def disconnect(self):
        """This method must be implemented in subclasses."""
        pass
