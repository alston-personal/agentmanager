from abc import ABC, abstractmethod
from typing import Any, Dict
from .models import SessionContext

class ContextProviderInterface(ABC):
    """Provides memory, identity, and environmental context to the runtime."""
    
    @abstractmethod
    def load_context(self) -> SessionContext:
        pass
        
    @abstractmethod
    def persist_session_close(self, payload: Dict[str, Any]) -> None:
        pass

class ExecutorInterface(ABC):
    """Abstract interface for task execution (e.g., shell commands, browser scripts)."""
    
    @abstractmethod
    def execute(self, task_definition: Dict[str, Any]) -> Dict[str, Any]:
        pass

class SessionManagerInterface(ABC):
    """Manages the lifecycle of an agent session."""
    
    @abstractmethod
    def start_session(self) -> str:
        pass
        
    @abstractmethod
    def close_session(self, session_id: str, summary: str) -> None:
        pass
