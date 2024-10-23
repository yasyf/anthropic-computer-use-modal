from asyncio import sleep
from uuid import uuid4

from rich import print

from computer_use_modal import ComputerUseServer, SandboxManager
from computer_use_modal.modal import app


@app.local_entrypoint()
async def demo(request_id: str = uuid4().hex):
    sandbox = SandboxManager(request_id=request_id)
    print("[bold]Debug URLs:[/bold]", await sandbox.debug_urls.remote.aio())

    server = ComputerUseServer()
    res = await server.messages_create.remote.aio(
        request_id=request_id,
        user_messages=[
            {"role": "user", "content": "What is the weather in San Francisco?"}
        ],
    )
    print("[bold]Response:[/bold]", res)
    await sleep(100000)
