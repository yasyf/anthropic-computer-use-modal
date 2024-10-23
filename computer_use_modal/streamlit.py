import asyncio
import base64
from enum import StrEnum
from typing import cast
from uuid import uuid4

import streamlit as st
from anthropic.types import TextBlock
from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock
from anthropic.types.tool_use_block import ToolUseBlock
from modal import Cls

from computer_use_modal import ComputerUseServer, app
from computer_use_modal.tools.base import ToolResult

STREAMLIT_STYLE = """
<style>
    /* Hide chat input while agent loop is running */
    .stApp[data-teststate=running] .stChatInput textarea,
    .stApp[data-test-script-state=running] .stChatInput textarea {
        display: none;
    }
     /* Hide the streamlit deploy button */
    .stDeployButton {
        visibility: hidden;
    }
</style>
"""


class Sender(StrEnum):
    USER = "user"
    BOT = "assistant"
    TOOL = "tool"


def setup_state():
    st.session_state.last_role = None
    st.session_state.request_id = uuid4().hex


async def main():
    setup_state()

    st.markdown(STREAMLIT_STYLE, unsafe_allow_html=True)
    st.title("Modal Computer Use Demo")

    new_message = st.chat_input(
        "Type a message to send to Claude to control the computer..."
    )

    if new_message:
        st.session_state.last_role = Sender.USER
        _render_message(Sender.USER, new_message)

    if st.session_state.last_role is not Sender.USER:
        return

    with st.spinner("Running Agent..."):
        res = Cls.lookup(
            app.name, ComputerUseServer.__name__
        ).messages_create.remote_gen.aio(
            request_id=st.session_state.request_id,
            user_messages=[{"role": "user", "content": new_message}],
        )
        async for msg in res:
            if msg.__class__.__name__ == "ToolResult":
                _render_message(Sender.TOOL, msg)
                st.session_state.last_role = Sender.TOOL
            else:
                st.session_state.last_role = msg["role"]
                if isinstance(msg["content"], str):
                    _render_message(msg["role"], msg["content"])
                elif isinstance(msg["content"], list):
                    for block in msg["content"]:
                        if isinstance(block, dict) and block["type"] == "tool_result":
                            continue
                        _render_message(
                            msg["role"],
                            cast(BetaTextBlock | BetaToolUseBlock, block),
                        )


def _render_message(
    sender: Sender,
    message: str | BetaTextBlock | BetaToolUseBlock | ToolResult,
):
    with st.chat_message(sender):
        if sender == Sender.TOOL:
            message = cast(ToolResult, message)
            if message.output and message.output.strip():
                st.code(message.output)
            if message.error and message.error.strip():
                st.error(message.error)
            if message.base64_image:
                st.image(base64.b64decode(message.base64_image))
        elif isinstance(message, BetaTextBlock) or isinstance(message, TextBlock):
            if message.text:
                st.write(message.text)
        elif isinstance(message, BetaToolUseBlock) or isinstance(message, ToolUseBlock):
            st.code(f"Tool Use: {message.name}\nInput: {message.input}")
        elif message:
            st.markdown(message)


if __name__ == "__main__":
    asyncio.run(main())
