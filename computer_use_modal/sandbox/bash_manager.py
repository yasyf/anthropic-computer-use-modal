import asyncio
import logging
from dataclasses import dataclass, field, replace
from functools import cached_property
from io import StringIO
from typing import Any, AsyncIterator

from modal import Sandbox
from modal.container_process import ContainerProcess

from computer_use_modal.tools.base import ToolResult

logger = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class BashSession:
    session_id: str
    pid: int | None = None


@dataclass(kw_only=True)
class BashSessionManager:
    sandbox: Sandbox
    session: BashSession | None = None
    proc: ContainerProcess | None = None

    @cached_property
    def outputs(self) -> tuple[AsyncIterator[str], AsyncIterator[str]]:
        assert self.proc is not None
        return aiter(self.proc.stdout), aiter(self.proc.stderr)

    async def start(self) -> BashSession:
        if self.session:
            self.proc = ContainerProcess(
                self.session.session_id, _gross_modal_hack(self.sandbox)._client
            )
        else:
            self.proc = await self.sandbox.exec.aio("bash")
            process_id = _gross_modal_hack(self.proc)._process_id
            assert process_id is not None
            self.session = BashSession(session_id=process_id)
            self.session = replace(
                self.session, pid=int((await self.run("echo $BASHPID")).output.strip())
            )
        return self.session

    async def kill(self):
        assert self.session is not None
        proc = await self.sandbox.exec.aio("kill", str(self.session.pid))
        await proc.wait.aio()
        self.session = None

    async def run(self, command: str) -> ToolResult:
        assert self.session is not None
        if not self.proc:
            await self.start()
        cmd = BashCommandManager(session=self)
        await cmd.start(command)
        res = await cmd.wait()
        if cmd.exit_code:
            await self.kill()
        return res


@dataclass(kw_only=True)
class BashCommandManager:
    SENTINEL = "<<exit>>"

    session: BashSessionManager

    stdout: StringIO = field(default_factory=StringIO)
    stderr: StringIO = field(default_factory=StringIO)
    timeout: float = 30

    exit_code: int | None = None

    @property
    def proc(self) -> ContainerProcess:
        assert self.session.proc is not None
        return self.session.proc

    async def start(self, command: str):
        assert self.proc is not None
        logger.info(f"running command: {command}")
        self.proc.stdin.write(f"{command}; echo '{self.SENTINEL}'\n")
        await self.proc.stdin.drain.aio()

    async def _wait(self):
        assert self.proc is not None

        stdout = asyncio.create_task(anext(self.session.outputs[0]))
        stderr = asyncio.create_task(anext(self.session.outputs[1]))
        wait = asyncio.create_task(self.proc.wait.aio())

        while True:
            done, _ = await asyncio.wait(
                tasks := (stdout, stderr, wait),
                return_when=asyncio.FIRST_COMPLETED,
                timeout=self.timeout,
            )
            if not done:
                logger.info(f"command timed out: {self.timeout} seconds")
                self.stderr.write(
                    f"timed out: bash has not returned in {self.timeout} seconds and must be restarted"
                )
                self.exit_code = -999
                break
            if stderr.done() and not stderr.exception():
                self.stderr.write(line := stderr.result())
                logger.info(f"stderr: {line}")
                stderr = asyncio.create_task(anext(self.session.outputs[1]))
            if stdout.done() and not stdout.exception():
                self.stdout.write(line := stdout.result())
                logger.info(f"stdout: {line}")
                if self.SENTINEL in self.stdout.getvalue():
                    break
                stdout = asyncio.create_task(anext(self.session.outputs[0]))
            if wait.done():
                logger.info(f"command exited with code {wait.result()}")
                self.exit_code = wait.result()
                if not self.stdout.getvalue() and (
                    output := await self.proc.stdout.read.aio()
                ):
                    logger.info(f"stdout: {output}")
                    self.stdout.write(output)
                if not self.stderr.getvalue() and (
                    error := await self.proc.stderr.read.aio()
                ):
                    logger.info(f"stderr: {error}")
                    self.stderr.write(error)
                self.stderr.write(f"bash has exited with returncode {self.exit_code}")
                break

        for t in tasks:
            t.cancel()

    async def wait(self):
        await self._wait()
        output = self.stdout.getvalue()
        try:
            output = output[: output.index(self.SENTINEL)]
        except ValueError:
            pass
        return ToolResult(
            output=output,
            error=self.stderr.getvalue(),
            system="tool must be restarted" if self.exit_code else None,
        )


def _gross_modal_hack(obj: Any):
    for k, v in obj.__dict__.items():
        if k.startswith("_sync_original_"):
            return v
    return obj
