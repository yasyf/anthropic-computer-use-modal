import asyncio
import shlex
from dataclasses import dataclass
from functools import singledispatchmethod

from anthropic.types.beta import BetaToolComputerUse20241022Param
from pydantic import ValidationError

from computer_use_modal.tools.base import BaseTool, ToolError, ToolResult
from computer_use_modal.tools.computer.types import (
    BaseComputerRequest,
    CursorPositionRequest,
    DoubleClickRequest,
    KeyRequest,
    LeftClickDragRequest,
    LeftClickRequest,
    MiddleClickRequest,
    MouseMoveRequest,
    RightClickRequest,
    ScreenshotRequest,
    TypeRequest,
)
from computer_use_modal.vnd.anthropic.tools.computer import (
    ComputerToolMixin,
    ScalingSource,
)


@dataclass(kw_only=True)
class ComputerTool(BaseTool[BetaToolComputerUse20241022Param], ComputerToolMixin):
    width: int = 1024
    height: int = 768
    display_num: int = 1

    @property
    def options(self) -> BetaToolComputerUse20241022Param:
        width, height = self.scale_coordinates(
            ScalingSource.COMPUTER, self.width, self.height
        )
        return {
            "name": "computer",
            "type": "computer_20241022",
            "display_width_px": width,
            "display_height_px": height,
            "display_number": self.display_num,
        }

    def _command(self, *args):
        return (f"DISPLAY=:{self.display_num}", "xdotool") + args

    async def __call__(
        self,
        /,
        **data,
    ):
        try:
            request = BaseComputerRequest.parse(data)
        except ValidationError as e:
            raise ToolError(f"Invalid tool parameters:\n{e.json()}") from e
        return await self.dispatch(request)

    @singledispatchmethod
    async def dispatch(self, request: BaseComputerRequest) -> ToolResult:
        raise ToolError(f"Unknown action: {request.action}")

    @dispatch.register(MouseMoveRequest)
    async def mouse_move(self, request: MouseMoveRequest):
        x, y = self.scale_coordinates(
            ScalingSource.API, request.coordinate[0], request.coordinate[1]
        )
        return await self.execute(*self._command("mousemove", "--sync", x, y))

    @dispatch.register(LeftClickDragRequest)
    async def left_click_drag(self, request: LeftClickDragRequest):
        x, y = self.scale_coordinates(
            ScalingSource.API, request.coordinate[0], request.coordinate[1]
        )
        return await self.execute(
            *self._command("mousedown", 1, "mousemove", "--sync", x, y, "mouseup", 1)
        )

    @dispatch.register(KeyRequest)
    async def key(self, request: KeyRequest):
        return await self.execute(*self._command("key", "--", request.text))

    @dispatch.register(TypeRequest)
    async def type(self, request: TypeRequest):
        results = [
            await self.execute(
                *self._command(
                    "type", "--delay", self.TYPING_DELAY_MS, "--", shlex.quote(chunk)
                )
            )
            for chunk in self.chunks(request.text, self.TYPING_GROUP_SIZE)
        ]
        result = sum(results, ToolResult())
        return result.replace(base64_image=(await self.screenshot()).base64_image)

    @dispatch.register(LeftClickRequest)
    async def left_click(self, request: LeftClickRequest):
        return await self.execute(*self._command("click", "1"))

    @dispatch.register(RightClickRequest)
    async def right_click(self, request: RightClickRequest):
        return await self.execute(*self._command("click", "3"))

    @dispatch.register(DoubleClickRequest)
    async def double_click(self, request: DoubleClickRequest):
        return await self.execute(
            *self._command("click", "--repeat", "2", "--delay", "500", "1")
        )

    @dispatch.register(MiddleClickRequest)
    async def middle_click(self, request: MiddleClickRequest):
        return await self.execute(*self._command("click", "2"))

    @dispatch.register(CursorPositionRequest)
    async def cursor_position(self, request: CursorPositionRequest):
        import re

        result = await self.execute(
            *self._command("getmouselocation", "--shell"), take_screenshot=False
        )
        if not result.output:
            raise ToolError("Failed to get cursor position")
        x, y = self.scale_coordinates(
            ScalingSource.COMPUTER,
            *map(int, re.match(r"X=(\d+).*Y=(\d+)", result.output).groups()),
        )
        return result.replace(output=f"X={x},Y={y}")

    @dispatch.register(ScreenshotRequest)
    async def screenshot(self, request: ScreenshotRequest):
        return await self.manager.take_screenshot.remote.aio(
            self.display_num,
            self.scale_coordinates(ScalingSource.COMPUTER, self.width, self.height),
        )

    async def execute(self, command: str, *args, take_screenshot: bool = True):
        result = await super().execute(command, *args)
        if not take_screenshot:
            return result
        await asyncio.sleep(self.SCREENSHOT_DELAY_S)
        return result + await self.screenshot()
