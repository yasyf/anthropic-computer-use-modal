import asyncio
import logging
from dataclasses import dataclass
from functools import cached_property
from typing import AsyncIterator, Literal

from modal.container_process import ContainerProcess

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class IOChunk:
    data: str
    stream: Literal["stdout", "stderr"]
    exit_code: int | None = None


@dataclass(frozen=True, kw_only=True)
class IOTask:
    proc: ContainerProcess
    timeout: float
    queue: asyncio.Queue[IOChunk]

    @cached_property
    def iters(self) -> tuple[AsyncIterator[str], AsyncIterator[str]]:
        return aiter(self.proc.stdout), aiter(self.proc.stderr)

    async def _select(self, tasks: list[asyncio.Task]):
        done, _ = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
            timeout=self.timeout,
        )
        if not done:  # timeout
            await self.queue.put(
                IOChunk(
                    data=f"timed out: bash has not output anything in {self.timeout} seconds and must be restarted",
                    stream="stderr",
                    exit_code=-999,
                )
            )
            return True

        if tasks[1].done() and not tasks[1].exception():
            await self.queue.put(IOChunk(data=tasks[1].result(), stream="stderr"))
            tasks[1] = asyncio.create_task(anext(self.iters[1]))
        if tasks[0].done() and not tasks[0].exception():
            await self.queue.put(IOChunk(data=tasks[0].result(), stream="stdout"))
            tasks[0] = asyncio.create_task(anext(self.iters[0]))
        if tasks[2].done():
            exit_code = tasks[2].result()
            await self.queue.put(
                IOChunk(
                    data=f"error: bash has exited with returncode {exit_code} and must be restarted",
                    stream="stderr",
                    exit_code=exit_code,
                )
            )
            return True

    async def run(self):
        logger.warning("io task started")
        tasks: list[asyncio.Task] = [
            asyncio.create_task(anext(self.iters[0])),
            asyncio.create_task(anext(self.iters[1])),
            asyncio.create_task(self.proc.wait.aio()),
        ]

        try:
            while True:
                if await self._select(tasks):
                    break
        finally:
            for task in tasks:
                task.cancel()
