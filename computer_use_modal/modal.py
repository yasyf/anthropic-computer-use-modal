import base64

from modal import App, Image, Secret

MOUNT_PATH = "/mnt/nfs"

app = App("anthropic-computer-use-modal")

FIREFOX_PIN = base64.b64encode(
    """
    Package: *
    Pin: release o=LP-PPA-mozillateam
    Pin-Priority: 1001

    Package: firefox
    Pin: version 1:1snap*
    Pin-Priority: -1
    """.encode()
).decode()

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
sandbox_image = (
    Image.from_registry(
        "ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest",
    )
    .workdir("/home/computeruse")
    .run_commands(
        "sed -i 's|Exec=firefox-esr -new-window|Exec=sudo firefox-esr -new-window|' /home/computeruse/.config/tint2/applications/firefox-custom.desktop",
        "add-apt-repository ppa:mozillateam/ppa",
        f"echo '{FIREFOX_PIN}' | base64 --decode | tee /etc/apt/preferences.d/mozilla-firefox",
        "apt-get update -y && apt-get install -y firefox-esr",
        "apt remove -y xdg-desktop-portal",
    )
)
secrets = Secret.from_local_environ(["ANTHROPIC_API_KEY"])
