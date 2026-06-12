from abc import ABC, abstractmethod
from typing import Any, Dict
from .models import SessionContext

class ContextProviderInterface(ABC):
    """Provides memory, identity, and environmental context to the runtime."""
    
    @abstractmethod
    def load_context(self) -> SessionContext:
        pass
        
    @abstractmethod
    def persist_session_close(self, payload: Dict[str, Any]) -> tuple[str, str]:
        """
        Persists the session close event to host storage.
        Returns:
            tuple[str, str]: A tuple of (record_uri, compact_entry) where
                record_uri is the host-specific path/URI to the saved record,
                compact_entry is a host-specific string summarizing the close.
        """
        pass

class ExecutorInterface(ABC):
    """Abstract interface for task execution (e.g., shell commands, browser scripts)."""
    
    @abstractmethod
    def execute(self, task_definition: Dict[str, Any]) -> Dict[str, Any]:
        pass
