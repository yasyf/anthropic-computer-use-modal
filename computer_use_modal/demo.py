from asyncio import sleep
from uuid import uuid4

from rich import print

from computer_use_modal.modal import app
from computer_use_modal.sandbox.sandbox_manager import SandboxManager


@app.local_entrypoint()
async def demo(request_id: str = uuid4().hex):
    sandbox = SandboxManager(request_id=request_id)
    print(f"[bold]Debug URL:[/bold] {await sandbox.debug_url.remote.aio()}")
    await sleep(100000)
