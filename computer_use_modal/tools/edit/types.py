from pathlib import Path
from typing import Annotated, Literal, Union

from annotated_types import Gt, Len
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from computer_use_modal.vnd.anthropic.tools.edit import Command


class BaseEditRequest(BaseModel):
    action: Command
    path: Path

    @classmethod
    def parse(cls, data: dict):
        adapter: TypeAdapter[TRequest] = TypeAdapter(
            Annotated[TRequest, Field(discriminator="action")]
        )
        return adapter.validate_python(data)

    @field_validator("path")
    def validate_path(cls, v: str | Path):
        if isinstance(v, str):
            v = Path(v)

        if not v.is_absolute():
            raise ValidationError(
                f"The path {v} is not an absolute path, it should start with `/`. Maybe you meant {Path("") / v}?"
            )
        return v


class ViewRequest(BaseEditRequest):
    action: Literal["view"] = "view"
    view_range: Annotated[tuple[int, int], Len(2, 2), Gt(0)] | None = None


class CreateRequest(BaseEditRequest):
    action: Literal["create"] = "create"
    file_text: str


class StrReplaceRequest(BaseEditRequest):
    action: Literal["str_replace"] = "str_replace"
    old_str: str
    new_str: str = ""

    @field_validator("old_str", "new_str")
    def validate_strs(cls, v: str):
        return v.expandtabs()


class InsertRequest(BaseEditRequest):
    action: Literal["insert"] = "insert"
    insert_line: int
    new_str: str

    @field_validator("new_str")
    def validate_strs(cls, v: str):
        return v.expandtabs()


class UndoEditRequest(BaseEditRequest):
    action: Literal["undo_edit"] = "undo_edit"


TRequest = Union[
    ViewRequest, CreateRequest, StrReplaceRequest, InsertRequest, UndoEditRequest
]