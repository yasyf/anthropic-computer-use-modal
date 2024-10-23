import asyncio
import logging
from dataclasses import dataclass, field, replace
from io import StringIO
from typing import Any

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

    async def start(self) -> BashSession:
        proc: ContainerProcess = await self.sandbox.exec.aio("bash")
        process_id = _gross_modal_hack(proc)._process_id
        assert process_id is not None
        self.session = BashSession(session_id=process_id)
        self.session = replace(
            self.session, pid=int((await self.run("echo", "$BASHPID")).output.strip())
        )
        return self.session

    async def kill(self):
        assert self.session is not None
        proc = await self.sandbox.exec.aio("kill", self.session.pid)
        await proc.wait.aio()
        self.session = None

    async def run(self, *command: str) -> ToolResult:
        assert self.session is not None
        cmd = BashCommandManager(sandbox=self.sandbox, session=self.session)
        await cmd.start(*command)
        return await cmd.wait()


@dataclass(kw_only=True)
class BashCommandManager:
    SENTINEL = "<<exit>>"

    sandbox: Sandbox
    session: BashSession

    stdout: StringIO = field(default_factory=StringIO)
    stderr: StringIO = field(default_factory=StringIO)
    timeout: float = 60

    proc: ContainerProcess | None = None
    exit_code: int | None = None

    async def start(self, *command: str):
        self.proc = ContainerProcess(
            self.session.session_id, _gross_modal_hack(self.sandbox)._client
        )
        self.proc.stdin.write(f"{' '.join(command)}; echo '{self.SENTINEL}'\n")
        await self.proc.stdin.drain.aio()

    async def _wait(self):
        assert self.proc is not None
        stdout_io, stderr_io = aiter(self.proc.stdout), aiter(self.proc.stderr)
        stdout = asyncio.create_task(anext(stdout_io))
        stderr = asyncio.create_task(anext(stderr_io))
        wait = asyncio.create_task(self.proc.wait.aio())

        while True:
            done, _ = await asyncio.wait(
                tasks := (stdout, stderr, wait),
                return_when=asyncio.FIRST_COMPLETED,
                timeout=self.timeout,
            )
            if not done:
                self.stderr.write(
                    f"timed out: bash has not returned in {self.timeout} seconds and must be restarted"
                )
                self._exit_code = -1
                break
            if stderr.done():
                self.stderr.write(line := stderr.result())
                logger.info(f"stderr: {line}")
                stderr = asyncio.create_task(anext(stderr_io))
            if stdout.done():
                self.stdout.write(line := stdout.result())
                logger.info(f"stdout: {line}")
                if self.SENTINEL in self.stdout.getvalue():
                    break
                stdout = asyncio.create_task(anext(stdout_io))
            if wait.done():
                self.exit_code = wait.result()
                break

        for t in tasks:
            t.cancel()

    async def wait(self):
        await self._wait()
        if self.exit_code and self.exit_code > 0:
            return ToolResult(
                system="tool must be restarted",
                error=f"bash has exited with returncode {self.exit_code}",
            )
        output = self.stdout.getvalue()
        try:
            output = output[: output.index(self.SENTINEL)]
        except ValueError:
            pass
        return ToolResult(output=output, error=self.stderr.getvalue())


def _gross_modal_hack(obj: Any):
    for k, v in obj.__dict__.items():
        if k.startswith("_sync_original_"):
            return v
    return obj
