import logging
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

logger = logging.getLogger(__name__)

class ToolError(_ToolError): ...


@dataclass(kw_only=True, frozen=True)
class ToolResult(_ToolResult):
    tool_use_id: str | None = None
    is_error: bool = False

    def __add__(self, other: "ToolResult"):
        result = super().__add__(other)
        return result.replace(
            is_error=self.is_error or other.is_error,
            tool_use_id=self.combine_fields(
                self.tool_use_id, other.tool_use_id, concatenate=False
            ),
        )

    def is_empty(self) -> bool:
        return not (self.error or self.output or self.base64_image or self.system)

    def to_api(self) -> BetaToolResultBlockParam:
        assert self.tool_use_id is not None, "tool_use_id is required"
        assert not self.is_empty(), "content is required"

        content: list[BetaTextBlockParam | BetaImageBlockParam] | str = []
        system = f"<system>{self.system}</system>\n" if self.system else ""

        if system:
            content.append({"type": "text", "text": system})
        if self.error:
            content.append({"type": "text", "text": self.error})
        if self.output:
            content.append({"type": "text", "text": self.output})
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
            "is_error": self.is_error,
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
            return ToolResult(error=f"Tool {name} is invalid", is_error=True)
        try:
            return await tool(**tool_input)
        except ToolError as e:
            logger.error(f"ToolError: {e}")
            return ToolResult(error=e.message, is_error=True)
        except Exception as e:
            logger.error(f"Exception: {e}")
            return ToolResult(error=str(e), is_error=True)

    async def run(self, *, name: str, tool_input: dict, tool_use_id: str) -> ToolResult:
        result = await self._run(name=name, tool_input=tool_input)
        result = result.replace(tool_use_id=tool_use_id)
        if result.is_empty():
            result = result.replace(output=f"{name} tool completed successfully")
        self.results.append(result)
        return result
