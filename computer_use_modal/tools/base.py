from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, Mapping, TypeVar

from anthropic.types.beta import (
    BetaImageBlockParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUnionParam,
)

from computer_use_modal.vnd.anthropic.tools.shared import ToolError as _ToolError
from computer_use_modal.vnd.anthropic.tools.shared import ToolResult as _ToolResult

if TYPE_CHECKING:
    from computer_use_modal.sandbox.sandbox_manager import SandboxManager

P = TypeVar("P", bound=Mapping)


class ToolError(_ToolError): ...


@dataclass(kw_only=True, frozen=True)
class ToolResult(_ToolResult):
    tool_use_id: str | None = None

    def to_api(self) -> BetaToolResultBlockParam:
        assert self.tool_use_id is not None, "tool_use_id is required"
        assert (
            self.error or self.output or self.base64_image or self.system
        ), "content is required"

        content: list[BetaTextBlockParam | BetaImageBlockParam] | str = []
        system = f"<system>{self.system}</system>\n" if self.system else ""

        if self.error:
            content = system + self.error
        else:
            if self.output:
                content.append({"type": "text", "text": system + self.output})
            if self.base64_image:
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": self.base64_image,
                        },
                    }
                )
        return {
            "type": "tool_result",
            "content": content,
            "tool_use_id": self.tool_use_id,
            "is_error": bool(self.error),
        }


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
    results: list[ToolResult] = field(default_factory=list)

    @property
    def tool_map(self) -> dict[str, BaseTool]:
        return {tool.options["name"]: tool for tool in self.tools}

    def to_params(
        self,
    ) -> list[BetaToolUnionParam]:
        return [tool.options for tool in self.tools]

    async def _run(self, *, name: str, tool_input: dict) -> ToolResult:
        tool = self.tool_map.get(name)
        if not tool:
            return ToolResult(error=f"Tool {name} is invalid")
        try:
            return await tool(**tool_input)
        except ToolError as e:
            return ToolResult(error=e.message)

    async def run(self, *, name: str, tool_input: dict, tool_use_id: str) -> ToolResult:
        result = await self._run(name=name, tool_input=tool_input)
        result = result.replace(tool_use_id=tool_use_id)
        self.results.append(result)
        return result
