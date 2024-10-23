import modal
from modal import App, Image, Sandbox, Volume

app = App.lookup("anthropic-computer-use-modal", create_if_missing=True)
image = (
    Image.debian_slim(python_version="3.13")
    .pip_install("uv")
    .run_commands("uv pip install -U 'anthropic>=0.37.1'")
)


@app.cls(image=image, concurrency_limit=1, allow_concurrent_inputs=10, timeout=60 * 20)
class SandboxManager:
    request_id: str = modal.parameter()
    auto_cleanup: bool = modal.parameter(default=True)

    @modal.enter()
    async def create_sandbox(self):
        self.volume = await Volume.lookup.aio(
            f"anthropic-computer-use-{self.request_id}", create_if_missing=True
        )
        if sandbox := await anext(
            Sandbox.list.aio(tags={"request_id": self.request_id}), None
        ):
            self.sandbox = sandbox
        else:
            self.sandbox = await Sandbox.create.aio(
                image=image,
                volumes={"/data": self.volume},
                timeout=60 * 20,
            )

    @modal.exit()
    async def cleanup_sandbox(self):
        if not self.auto_cleanup:
            return
        await self.sandbox.terminate.aio()
        await self.volume.delete.aio()
