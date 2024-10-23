from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Mapping, TypeVar

from computer_use_modal.vnd.anthropic.tools.shared import ToolError as _ToolError
from computer_use_modal.vnd.anthropic.tools.shared import ToolResult as _ToolResult

if TYPE_CHECKING:
    from computer_use_modal.sandbox.sandbox_manager import SandboxManager

P = TypeVar("P", bound=Mapping)


class ToolError(_ToolError): ...


class ToolResult(_ToolResult): ...


@dataclass(kw_only=True)
class BaseTool(ABC, Generic[P]):
    manager: SandboxManager

    @property
    @abstractmethod
    def options(self) -> P: ...

    @abstractmethod
    async def __call__(self, /, **kwargs): ...

    async def execute(self, command: str, *args):
        return await self.manager.run_command.remote.aio(command, *args)
