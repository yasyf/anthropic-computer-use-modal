import asyncio
import base64
from uuid import uuid4

from rich import print

from computer_use_modal import ComputerUseServer, SandboxManager
from computer_use_modal.app import app
from computer_use_modal.tools.base import ToolResult


@app.local_entrypoint()
async def demo(request_id: str = uuid4().hex):
    sandbox = SandboxManager(request_id=request_id)
    print("[bold]Debug URLs:[/bold]", await sandbox.debug_urls.remote.aio())

    server = ComputerUseServer()
    res = server.messages_create.remote_gen.aio(
        request_id=request_id,
        user_messages=[
            {
                "role": "user",
                "content": "print a cow in bash, then write it to a file, and add a fun joke to the top of the file using the edit tool",
            }
        ],
    )
    async for msg in res:
        if isinstance(msg, ToolResult):
            if msg.base64_image:
                proc = await asyncio.create_subprocess_shell(
                    "viu -", stdin=asyncio.subprocess.PIPE
                )
                await proc.communicate(base64.b64decode(msg.base64_image))
                await proc.wait()
            else:
                print("[bold]Tool Result:[/bold]", msg)
        elif isinstance(msg, dict) and msg["role"] == "assistant":
            print("[bold]Response:[/bold]", msg)
