from dataclasses import dataclass, field, fields, replace


class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message


@dataclass(kw_only=True, frozen=True)
class ToolResult:
    """Represents the result of a tool execution."""

    output: str | None = None
    error: str | None = None
    base64_image: str | None = field(default=None, repr=False)
    system: str | None = None

    def __bool__(self):
        return any(getattr(self, field.name) for field in fields(self))

    @staticmethod
    def combine_fields(
        field: str | None, other_field: str | None, concatenate: bool = True
    ):
            if field and other_field:
                if concatenate:
                    return field + "\n" + other_field
                raise ValueError("Cannot combine tool results")
            return field or other_field

    def __add__(self, other: "ToolResult"):
        return self.__class__(
            output=self.combine_fields(self.output, other.output),
            error=self.combine_fields(self.error, other.error),
            base64_image=self.combine_fields(
                self.base64_image, other.base64_image, False
            ),
            system=self.combine_fields(self.system, other.system),
        )

    def replace(self, **kwargs):
        """Returns a new ToolResult with the given fields replaced."""
        return replace(self, **kwargs)
