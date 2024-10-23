import asyncio
import base64
from enum import StrEnum
from typing import cast
from uuid import uuid4

import streamlit as st
from anthropic.types import TextBlock
from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock
from anthropic.types.tool_use_block import ToolUseBlock

from computer_use_modal import ComputerUseServer
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
    st.session_state.messages = []
    st.session_state.responses = {}
    st.session_state.tools = {}
    st.session_state.request_id = uuid4().hex


async def main():
    setup_state()

    st.markdown(STREAMLIT_STYLE, unsafe_allow_html=True)
    st.title("Modal Computer Use Demo")

    chat, http_logs = st.tabs(["Chat", "HTTP Exchange Logs"])
    new_message = st.chat_input(
        "Type a message to send to Claude to control the computer..."
    )

    with chat:
        for message in st.session_state.messages:
            if isinstance(message["content"], str):
                _render_message(message["role"], message["content"])
            elif isinstance(message["content"], list):
                for block in message["content"]:
                    if isinstance(block, dict) and block["type"] == "tool_result":
                        _render_message(
                            Sender.TOOL, st.session_state.tools[block["tool_use_id"]]
                        )
                    else:
                        _render_message(
                            message["role"],
                            cast(BetaTextBlock | BetaToolUseBlock, block),
                        )

        if new_message:
            st.session_state.messages.append(
                {
                    "role": Sender.USER,
                    "content": [TextBlock(type="text", text=new_message)],
                }
            )
            _render_message(Sender.USER, new_message)

        try:
            most_recent_message = st.session_state["messages"][-1]
        except IndexError:
            return

        if most_recent_message["role"] is not Sender.USER:
            return

        with st.spinner("Running Agent..."):
            res = ComputerUseServer().messages_create.remote_gen.aio(
                request_id=st.session_state.request_id,
                user_messages=[
                    {"role": "user", "content": "What is the weather in San Francisco?"}
                ],
            )
            async for msg in res:
                if msg.__class__.__name__ == "ToolResult":
                    _render_message(Sender.TOOL, msg)
                    st.session_state.tools[msg.tool_use_id] = msg
                else:
                    _render_message(Sender.BOT, msg)


def _render_message(
    sender: Sender,
    message: str | BetaTextBlock | BetaToolUseBlock | ToolResult,
):
    with st.chat_message(sender):
        if sender == Sender.TOOL:
            message = cast(ToolResult, message)
            if message.output:
                st.code(message.output)
            if message.error:
                st.error(message.error)
            if message.base64_image:
                st.image(base64.b64decode(message.base64_image))
        elif isinstance(message, BetaTextBlock) or isinstance(message, TextBlock):
            st.write(message.text)
        elif isinstance(message, BetaToolUseBlock) or isinstance(message, ToolUseBlock):
            st.code(f"Tool Use: {message.name}\nInput: {message.input}")
        else:
            st.markdown(message)


if __name__ == "__main__":
    asyncio.run(main())
