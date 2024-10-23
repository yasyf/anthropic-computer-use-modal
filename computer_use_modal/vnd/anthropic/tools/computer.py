from enum import StrEnum
from typing import Literal, TypedDict

from .shared import ToolError

OUTPUT_DIR = "/tmp/outputs"

TYPING_DELAY_MS = 12
TYPING_GROUP_SIZE = 50

Action = Literal[
    "key",
    "type",
    "mouse_move",
    "left_click",
    "left_click_drag",
    "right_click",
    "middle_click",
    "double_click",
    "screenshot",
    "cursor_position",
]


class Resolution(TypedDict):
    width: int
    height: int


# sizes above XGA/WXGA are not recommended (see README.md)
# scale down to one of these targets if ComputerTool._scaling_enabled is set
MAX_SCALING_TARGETS: dict[str, Resolution] = {
    "XGA": Resolution(width=1024, height=768),  # 4:3
    "WXGA": Resolution(width=1280, height=800),  # 16:10
    "FWXGA": Resolution(width=1366, height=768),  # ~16:9
}


class ScalingSource(StrEnum):
    COMPUTER = "computer"
    API = "api"


class ComputerToolOptions(TypedDict):
    display_height_px: int
    display_width_px: int
    display_number: int | None


class ComputerToolMixin:
    TYPING_DELAY_MS = TYPING_DELAY_MS
    TYPING_GROUP_SIZE = TYPING_GROUP_SIZE
    SCREENSHOT_DELAY_S = 2

    width: int
    height: int

    @staticmethod
    def chunks(s: str, chunk_size: int) -> list[str]:
        return [s[i : i + chunk_size] for i in range(0, len(s), chunk_size)]

    def scale_coordinates(self, source: ScalingSource, x: int, y: int):
        """Scale coordinates to a target maximum resolution."""

        ratio = self.width / self.height
        target_dimension = next(
            (
                dimension
                for dimension in MAX_SCALING_TARGETS.values()
                if abs(dimension["width"] / dimension["height"] - ratio) < 0.02
                and dimension["width"] < self.width
            ),
            None,
        )
        if target_dimension is None:
            return x, y
        # should be less than 1
        x_scaling_factor = target_dimension["width"] / self.width
        y_scaling_factor = target_dimension["height"] / self.height
        if source == ScalingSource.API:
            if x > self.width or y > self.height:
                raise ToolError(f"Coordinates {x}, {y} are out of bounds")
            # scale up
            return round(x / x_scaling_factor), round(y / y_scaling_factor)
        # scale down
        return round(x * x_scaling_factor), round(y * y_scaling_factor)
