import asyncio
import logging
from dataclasses import dataclass, field, replace
from io import StringIO
from typing import Any, cast

from modal import Sandbox
from modal.container_process import ContainerProcess

from computer_use_modal.sandbox.io import IOChunk, IOTask
from computer_use_modal.tools.base import ToolResult

logger = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True, unsafe_hash=True)
class BashSession:
    session_id: str
    pid: int | None = None


@dataclass(kw_only=True)
class BashSessionManager:
    sandbox: Sandbox
    session: BashSession | None = None
    proc: ContainerProcess | None = None
    timeout: float = 30

    io_queue: asyncio.Queue[IOChunk] = field(default_factory=asyncio.Queue)
    _io_task: asyncio.Task | None = None

    async def start(self) -> BashSession:
        if self.session:
            self.proc = ContainerProcess(
                self.session.session_id, _gross_modal_hack(self.sandbox)._client
            )
        else:
            self.proc = cast(ContainerProcess, await self.sandbox.exec.aio("bash"))
            process_id = _gross_modal_hack(self.proc)._process_id
            assert process_id is not None
            self.session = BashSession(session_id=process_id)

        self._io_task = asyncio.create_task(
            IOTask(proc=self.proc, timeout=self.timeout, queue=self.io_queue).run()
        )

        if not self.session.pid:
            self.session = replace(
                self.session, pid=int((await self.run("echo $BASHPID")).output.strip())
            )

        return self.session

    async def kill(self):
        assert self.session is not None
        if self._io_task:
            self._io_task.cancel()
        logger.info(f"killing bash with pid {self.session.pid}")
        proc = await self.sandbox.exec.aio("kill", str(self.session.pid))
        await proc.wait.aio()
        self.session = None
        self.proc = None

    async def run(self, command: str) -> ToolResult:
        if not self.proc:
            await self.start()
        assert self.session is not None
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

    async def _loop(self):
        while True:
            chunk = await self.session.io_queue.get()
            if chunk.stream == "stdout":
                logger.info(f"stdout: {chunk.data}")
                self.stdout.write(chunk.data)
            elif chunk.stream == "stderr":
                logger.info(f"stderr: {chunk.data}")
                self.stderr.write(chunk.data)

            if chunk.exit_code is not None:
                logger.info(f"command exited with code {chunk.exit_code}")
                self.exit_code = chunk.exit_code
                break
            elif self.SENTINEL in self.stdout.getvalue():
                logger.info("command succeeded")
                break

    async def loop(self):
        try:
            async with asyncio.timeout(self.session.timeout):
                await self._loop()
        except asyncio.TimeoutError:
            self.stderr.write(
                f"timed out: bash has not returned in {self.session.timeout} seconds and must be restarted"
            )
            self.exit_code = -999

    async def wait(self):
        await self.loop()
        if self.SENTINEL in (output := self.stdout.getvalue()):
            output = output[: output.index(self.SENTINEL)]
        return ToolResult(
            output=output,
            error=self.stderr.getvalue(),
            system=(
                "tool must be restarted" if self.exit_code else "bash command succeeded"
            ),
        )


def _gross_modal_hack(obj: Any):
    for k, v in obj.__dict__.items():
        if k.startswith("_sync_original_"):
            return v
    return obj
