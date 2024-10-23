from modal import App, Image, Secret

MOUNT_PATH = "/mnt/nfs"

app = App("anthropic-computer-use-modal")

image = (
    Image.debian_slim(python_version="3.12")
    .env(
        {
            "UV_PROJECT_ENVIRONMENT": "/usr/local",
            "UV_COMPILE_BYTECODE": "1",
            "UV_LINK_MODE": "copy",
        }
    )
    .pip_install("uv")
    .copy_local_file("pyproject.toml")
    .copy_local_file("uv.lock")
    .run_commands("uv sync --frozen --inexact --no-dev")
)
sandbox_image = Image.from_registry(
    "ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest"
)
secrets = Secret.from_local_environ(["ANTHROPIC_API_KEY"])
