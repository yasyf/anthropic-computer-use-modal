from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Mapping, TypeVar

from anthropic.types.beta import BetaToolUnionParam

from computer_use_modal.vnd.anthropic.tools.shared import ToolError as _ToolError
from computer_use_modal.vnd.anthropic.tools.shared import ToolResult as _ToolResult

if TYPE_CHECKING:
    from computer_use_modal.sandbox.sandbox_manager import SandboxManager

P = TypeVar("P", bound=Mapping)


class ToolError(_ToolError): ...


class ToolResult(_ToolResult): ...


@dataclass(kw_only=True)
class BaseTool(ABC, Generic[P]):
    manager: "SandboxManager"

    @property
    @abstractmethod
    def options(self) -> P: ...

    @abstractmethod
    async def __call__(self, /, **kwargs) -> ToolResult: ...

    async def execute(self, command: str, *args):
        return await self.manager.run_command.remote.aio(command, *args)


@dataclass(kw_only=True, frozen=True)
class ToolCollection:
    tools: tuple[BaseTool, ...]

    @property
    def tool_map(self) -> dict[str, BaseTool]:
        return {tool.options["name"]: tool for tool in self.tools}

    def to_params(
        self,
    ) -> list[BetaToolUnionParam]:
        return [tool.options for tool in self.tools]

    async def run(self, *, name: str, tool_input: dict) -> ToolResult:
        tool = self.tool_map.get(name)
        if not tool:
            return ToolResult(error=f"Tool {name} is invalid")
        try:
            return await tool(**tool_input)
        except ToolError as e:
            return ToolResult(error=e.message)
