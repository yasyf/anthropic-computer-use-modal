from modal import App, Image

app = App.lookup("anthropic-computer-use-modal", create_if_missing=True)

image = (
    Image.debian_slim(python_version="3.13")
    .pip_install("uv")
    .copy_local_file("pyproject.toml")
    .copy_local_file("uv.lock")
    .run_commands("uv sync")
)
sandbox_image = Image.from_registry(
    "ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest"
)


from .sandbox_manager import SandboxManager  # noqa
