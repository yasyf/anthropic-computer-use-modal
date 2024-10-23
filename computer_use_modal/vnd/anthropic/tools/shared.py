from dataclasses import dataclass, fields, replace

from anthropic.types.beta import (
    BetaImageBlockParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
)


class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message


@dataclass(kw_only=True, frozen=True)
class ToolResult:
    """Represents the result of a tool execution."""

    output: str | None = None
    error: str | None = None
    base64_image: str | None = None
    system: str | None = None

    def __bool__(self):
        return any(getattr(self, field.name) for field in fields(self))

    def __add__(self, other: "ToolResult"):
        def combine_fields(
            field: str | None, other_field: str | None, concatenate: bool = True
        ):
            if field and other_field:
                if concatenate:
                    return field + other_field
                raise ValueError("Cannot combine tool results")
            return field or other_field

        return self.__class__(
            output=combine_fields(self.output, other.output),
            error=combine_fields(self.error, other.error),
            base64_image=combine_fields(self.base64_image, other.base64_image, False),
            system=combine_fields(self.system, other.system),
        )

    def replace(self, **kwargs):
        """Returns a new ToolResult with the given fields replaced."""
        return replace(self, **kwargs)

    def to_api(self, tool_use_id: str) -> BetaToolResultBlockParam:
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
            "tool_use_id": tool_use_id,
            "is_error": bool(self.error),
        }
