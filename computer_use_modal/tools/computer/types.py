from typing import Annotated, Literal, Union

from annotated_types import Gt, Len
from pydantic import BaseModel, Field, TypeAdapter

from computer_use_modal.vnd.anthropic.tools.computer import Action


class BaseComputerRequest(BaseModel):
    action: Action

    @classmethod
    def parse(cls, data: dict):
        adapter: TypeAdapter[TRequest] = TypeAdapter(
            Annotated[TRequest, Field(discriminator="action")]
        )
        return adapter.validate_python(data)


class CoordinateRequest(BaseComputerRequest):
    coordinate: Annotated[tuple[int, int], Len(2, 2), Gt(0)]


class MouseMoveRequest(CoordinateRequest):
    action: Literal["mouse_move"] = "mouse_move"


class LeftClickDragRequest(CoordinateRequest):
    action: Literal["left_click_drag"] = "left_click_drag"


class KeysRequest(BaseComputerRequest):
    text: str


class KeyRequest(KeysRequest):
    action: Literal["key"] = "key"


class TypeRequest(KeysRequest):
    action: Literal["type"] = "type"


class MouseRequest(BaseComputerRequest):
    pass


class LeftClickRequest(MouseRequest):
    action: Literal["left_click"] = "left_click"


class RightClickRequest(MouseRequest):
    action: Literal["right_click"] = "right_click"


class DoubleClickRequest(MouseRequest):
    action: Literal["double_click"] = "double_click"


class MiddleClickRequest(MouseRequest):
    action: Literal["middle_click"] = "middle_click"


class ScreenshotRequest(BaseComputerRequest):
    action: Literal["screenshot"] = "screenshot"


class CursorPositionRequest(BaseComputerRequest):
    action: Literal["cursor_position"] = "cursor_position"


TRequest = Union[
    MouseMoveRequest,
    LeftClickDragRequest,
    KeyRequest,
    TypeRequest,
    LeftClickRequest,
    RightClickRequest,
    DoubleClickRequest,
    MiddleClickRequest,
    ScreenshotRequest,
    CursorPositionRequest,
]
