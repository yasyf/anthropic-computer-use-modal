import asyncio
import logging
from io import BytesIO
from pathlib import Path

import backoff
import modal
from modal import NetworkFileSystem, Sandbox, SchedulerPlacement
from modal.container_process import ContainerProcess

from computer_use_modal.app import MOUNT_PATH, app, image, sandbox_image
from computer_use_modal.sandbox.bash_manager import BashSession, BashSessionManager
from computer_use_modal.tools.base import ToolResult

logger = logging.getLogger(__name__)

@app.cls(
    image=image,
    concurrency_limit=1,
    allow_concurrent_inputs=10,
    timeout=60 * 30,
    container_idle_timeout=60 * 20,
)
class SandboxManager:
    request_id: str = modal.parameter()
    auto_cleanup: int = modal.parameter(default=0)

    @modal.enter()
    async def create_sandbox(self):
        logging.basicConfig(level=logging.INFO)

        self.nfs = await NetworkFileSystem.lookup.aio(
            f"anthropic-computer-use-{self.request_id}", create_if_missing=True
        )
        if sandbox := await anext(
            Sandbox.list.aio(tags={"request_id": self.request_id}), None
        ):
            self.sandbox = sandbox
        else:
            self.sandbox = await Sandbox.create.aio(
                image=sandbox_image,
                cpu=4,
                memory=4096,
                network_file_systems={MOUNT_PATH: self.nfs},
                timeout=60 * 60,
                encrypted_ports=[8501, 6080],
                _experimental_scheduler_placement=SchedulerPlacement(region="us"),
            )
            logger.info("Waiting for sandbox to start...")
            await asyncio.sleep(15)
            logger.info("Sandbox started")

    @modal.exit()
    async def cleanup_sandbox(self):
        if not self.auto_cleanup:
            return
        await self.sandbox.terminate.aio()

    @modal.method()
    async def debug_urls(self):
        tunnels = await self.sandbox.tunnels.aio()
        return {
            "vnc": tunnels[6080].url,
            "webui": tunnels[8501].url,
        }

    @modal.method()
    async def run_command(self, *command: str) -> ToolResult:
        logger.info(f"Running command: {command}")
        proc: ContainerProcess = await self.sandbox.exec.aio(*map(str, command))
        await proc.wait.aio()
        res = ToolResult(
            output=await proc.stdout.read.aio(),
            error=await proc.stderr.read.aio(),
        )
        logger.info(f"Command returned: {res}")
        return res

    @backoff.on_exception(backoff.expo, FileNotFoundError, max_tries=3)
    async def read_file(self, path: Path) -> bytes:
        buff = BytesIO()
        async for chunk in self.nfs.read_file.aio(
            path.relative_to(MOUNT_PATH).as_posix()
        ):
            buff.write(chunk)
        buff.seek(0)
        return buff.getvalue()

    @modal.method()
    async def take_screenshot(self, display: int, size: tuple[int, int]) -> ToolResult:
        from base64 import b64encode

        from uuid6 import uuid7

        path = Path(MOUNT_PATH) / f"{uuid7().hex}.png"
        await self.run_command.local(
            "env",
            f"DISPLAY=:{display}",
            "scrot",
            "-p",
            path.as_posix(),
        )
        await self.run_command.local(
            "convert",
            path.as_posix(),
            "-resize",
            f"{size[0]}x{size[1]}!",
            path.as_posix(),
        )
        return ToolResult(base64_image=b64encode(await self.read_file(path)).decode())

    @modal.method()
    async def start_bash_session(self) -> BashSession:
        return await BashSessionManager(sandbox=self.sandbox).start()

    @modal.method()
    async def execute_bash_command(self, session: BashSession, *cmd: str) -> ToolResult:
        return await BashSessionManager(sandbox=self.sandbox, session=session).run(*cmd)

    @modal.method()
    async def end_bash_session(self, session: BashSession):
        await BashSessionManager(sandbox=self.sandbox, session=session).kill()
