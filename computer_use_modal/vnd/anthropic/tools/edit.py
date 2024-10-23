from typing import Literal

TRUNCATED_MESSAGE: str = "<response clipped><NOTE>To save on context only part of this file has been shown to you. You should retry this tool after you have searched inside the file with `grep -n` in order to find the line numbers of what you are looking for.</NOTE>"
MAX_RESPONSE_LEN: int = 16000


Command = Literal[
    "view",
    "create",
    "str_replace",
    "insert",
    "undo_edit",
]


def maybe_truncate(content: str, truncate_after: int | None = MAX_RESPONSE_LEN):
    """Truncate content and append a notice if content exceeds the specified length."""
    return (
        content
        if not truncate_after or len(content) <= truncate_after
        else content[:truncate_after] + TRUNCATED_MESSAGE
    )


def make_output(
    file_content: str,
    file_descriptor: str,
    init_line: int = 1,
):
    """Generate output for the CLI based on the content of a file."""
    file_content = maybe_truncate(file_content)
    file_content = file_content.expandtabs()
    file_content = "\n".join(
        [
            f"{i + init_line:6}\t{line}"
            for i, line in enumerate(file_content.split("\n"))
        ]
    )
    return (
        f"Here's the result of running `cat -n` on {file_descriptor}:\n"
        + file_content
        + "\n"
    )
