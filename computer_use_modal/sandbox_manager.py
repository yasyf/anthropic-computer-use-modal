from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import modal
from modal import NetworkFileSystem, Sandbox
from modal.container_process import ContainerProcess

from computer_use_modal.deploy import app, image, sandbox_image

if TYPE_CHECKING:
    from computer_use_modal.tools.base import ToolResult


@app.cls(image=image, concurrency_limit=1, allow_concurrent_inputs=10, timeout=60 * 20)
class SandboxManager:
    request_id: str = modal.parameter()
    auto_cleanup: bool = modal.parameter(default=True)

    @modal.enter()
    async def create_sandbox(self):
        self.nfs = await NetworkFileSystem.lookup.aio(
            f"anthropic-computer-use-{self.request_id}", create_if_missing=True
        )
        if sandbox := await anext(
            Sandbox.list.aio(tags={"request_id": self.request_id}), None
        ):
            self.sandbox = sandbox
        else:
            self.sandbox = await Sandbox.create.aio(
                "./entrypoint.sh",
                image=sandbox_image,
                network_file_systems={"/mnt/nfs": self.nfs},
                timeout=60 * 20,
                encrypted_ports=[8080],
            )

    @modal.exit()
    async def cleanup_sandbox(self):
        if not self.auto_cleanup:
            return
        await self.sandbox.terminate.aio()
        await self.volume.delete.aio()

    @modal.method()
    async def debug_url(self):
        return (await self.sandbox.tunnels.aio())[8080].url

    @modal.method()
    async def run_command(self, *command: str) -> "ToolResult":
        proc: ContainerProcess = await self.sandbox.exec.aio(*command)
        await proc.wait.aio()
        return ToolResult(
            output=await proc.stdout.read.aio(),
            error=await proc.stderr.read.aio(),
        )

    @modal.method()
    async def take_screenshot(
        self, display: int, size: tuple[int, int]
    ) -> "ToolResult":
        from base64 import b64encode

        from uuid6 import uuid7

        path = Path("/mnt/nfs") / f"{uuid7().hex}.png"
        await self.run_command.local(
            f"DISPLAY=:{display}", "gnome-screenshot", "-f", path.as_posix(), "-p"
        )
        await self.run_command.local(
            "convert",
            path.as_posix(),
            "-resize",
            f"{size[0]}x{size[1]}!",
            path.as_posix(),
        )
        buff = BytesIO()
        async for chunk in self.nfs.read_file.aio(
            path.relative_to("/mnt/nfs").as_posix()
        ):
            buff.write(chunk)
        buff.seek(0)
        return ToolResult(base64_image=b64encode(buff.getvalue()).decode())
