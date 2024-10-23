from collections import defaultdict
from dataclasses import dataclass, field
from functools import singledispatchmethod
from pathlib import Path
from typing import TYPE_CHECKING, Self

import modal
from modal.volume import FileEntry, FileEntryType

from computer_use_modal.modal import MOUNT_PATH
from computer_use_modal.tools.base import ToolError, ToolResult
from computer_use_modal.tools.edit.types import (
    CreateRequest,
    InsertRequest,
    StrReplaceRequest,
    TRequest,
    UndoEditRequest,
    ViewRequest,
)
from computer_use_modal.vnd.anthropic.tools.edit import make_output

if TYPE_CHECKING:
    from computer_use_modal.sandbox.sandbox_manager import SandboxManager

SESSIONS = modal.Dict.from_name("edit-sessions", create_if_missing=True)

@dataclass(frozen=True, kw_only=True)
class EditSession:
    file_versions: dict[Path, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )

    @classmethod
    async def from_request_id(cls, request_id: str) -> Self:
        return await SESSIONS.get.aio(request_id, cls())


@dataclass(kw_only=True, frozen=True)
class FileInfo:
    path: Path
    listing: list[FileEntry]
    manager: "EditSessionManager"

    def exists(self) -> bool:
        return bool(self.listing)

    def is_file(self) -> bool:
        return len(self.listing) == 1 and self.listing[0].type == FileEntryType.FILE

    def is_dir(self) -> bool:
        return self.exists and not self.is_file

    @property
    def local_path(self) -> Path:
        return Path(MOUNT_PATH) / self.path

    async def read(self) -> str:
        return (await self.manager.sandbox.read_file(self.path)).expandtabs()

    async def write(self, content: str):
        self.manager.session.file_versions[self.path].append(await self.read())
        await self.manager.sandbox.nfs.write_file.aio(self.path, content.expandtabs())

    def __str__(self) -> str:
        return self.path.as_posix()


@dataclass(kw_only=True, frozen=True)
class EditSessionManager:
    SNIPPET_LINES: int = 4

    sandbox: "SandboxManager"
    session: EditSession

    async def _validate_request(self, request: TRequest):
        info = FileInfo(
            path=request.path,
            listing=await self.sandbox.nfs.listdir.aio(request.path),
            manager=self,
        )
        if request.action != "create" and not info.exists():
            raise ToolError(
                f"The path {request.path} does not exist. Please provide a valid path."
            )
        if request.action == "create" and info.exists():
            raise ToolError(
                f"File already exists at: {request.path}. Cannot overwrite files using command `create`."
            )
        if request.action != "view" and info.is_dir():
            raise ToolError(
                f"The path {request.path} is a directory and only the `view` command can be used on directories"
            )
        if request.action == "view" and request.view_range and info.is_dir():
            raise ToolError(
                "The `view_range` parameter is not allowed when `path` points to a directory."
            )
        return info

    def _make_output(self, body: str, fname: str, start: int = 1):
        return ToolResult(output=make_output(body, fname, start))

    @singledispatchmethod
    async def dispatch(self, request: TRequest) -> ToolResult:
        raise ToolError(f"Action {request.action} not supported")

    @dispatch.register
    async def view(self, request: ViewRequest):
        f = await self._validate_request(request)
        if f.is_dir():
            res = await self.sandbox.run_command.local(
                "find", str(f.local_path), "-maxdepth", "2", "-not", "-path", r"'*/\.*'"
            )
            if res.output:
                return (
                    ToolResult(
                        output=f"Here's the files and directories up to 2 levels deep in {f}, excluding hidden items"
                    )
                    + res
                )
            else:
                return res

        lines = (await f.read()).splitlines(keepends=True)
        (start, end) = request.view_range or (1, -1)
        start, end = (
            max(1, start),
            min(len(lines) + 1, len(lines) + 1 if end == -1 else end),
        )
        return self._make_output(
            body="\n".join(lines[start - 1 : end]),
            fname=str(f),
            start=start,
        )

    @dispatch.register(CreateRequest)
    async def create(self, request: CreateRequest):
        f = await self._validate_request(request)
        await f.write(request.file_text)
        return ToolResult(output=f"File created successfully at: {f}")

    async def _make_snippet(
        self, f: FileInfo, center: int, length: int = SNIPPET_LINES
    ):
        start, end = max(0, center - length), center + length
        snippet = "\n".join((await f.read()).split("\n")[start : end + 1])
        return self._make_output(snippet, f"a snippet of {f}", start + 1)

    @dispatch.register(StrReplaceRequest)
    async def str_replace(self, request: StrReplaceRequest):
        f = await self._validate_request(request)
        content = await f.read()

        if (occurrences := content.count(request.old_str)) == 0:
            raise ToolError(
                f"No replacement was performed, old_str `{request.old_str}` did not appear verbatim in {f}."
            )
        elif occurrences > 1:
            lines = [
                idx + 1
                for idx, line in enumerate(content.split("\n"))
                if request.old_str in line
            ]
            raise ToolError(
                f"No replacement was performed. Multiple occurrences of old_str `{request.old_str}` in lines {lines}. Please ensure it is unique."
            )

        await f.write(content.replace(request.old_str, request.new_str))
        replacement = content.split(request.old_str)[0].count("\n")

        return (
            ToolResult(output=f"The file {f} has been edited. ")
            + await self._make_snippet(
                f,
                replacement,
                length=self.SNIPPET_LINES + len(request.new_str.splitlines()),
            )
            + ToolResult(
                output="Review the changes and make sure they are as expected. Edit the file again if necessary."
            )
        )

    @dispatch.register(InsertRequest)
    async def insert(self, request: InsertRequest):
        f = await self._validate_request(request)
        content = await f.read()
        lines = content.splitlines(keepends=True)

        if request.insert_line < 0 or request.insert_line > len(lines):
            raise ToolError(
                f"Invalid `insert_line` parameter: {request.insert_line}. It should be within the range of lines of the file: {[0, len(lines)]}"
            )

        lines = (
            lines[: request.insert_line]
            + request.new_str.splitlines(keepends=True)
            + lines[request.insert_line :]
        )
        await f.write("\n".join(lines))

        return (
            ToolResult(output=f"The file {f} has been edited. ")
            + await self._make_snippet(
                f,
                request.insert_line,
                length=self.SNIPPET_LINES + len(request.new_str.splitlines()),
            )
            + ToolResult(
                output="Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary."
            )
        )

    @dispatch.register(UndoEditRequest)
    async def undo_edit(self, request: UndoEditRequest):
        f = await self._validate_request(request)
        await f.write(old_content := self.session.file_versions[f.path].pop())
        return ToolResult(
            output=f"Last edit to {f} undone successfully."
        ) + self._make_output(old_content, str(f))
