import logging
from typing import AsyncGenerator, cast

import modal
from anthropic import Anthropic
from anthropic.types.beta import (
    BetaContentBlock,
    BetaContentBlockParam,
    BetaMessageParam,
)

from computer_use_modal.app import app, image, secrets
from computer_use_modal.sandbox.sandbox_manager import SandboxManager
from computer_use_modal.server.messages import Messages
from computer_use_modal.server.prompts import SYSTEM_PROMPT
from computer_use_modal.tools.base import ToolCollection, ToolResult
from computer_use_modal.tools.bash import BashTool
from computer_use_modal.tools.computer.computer import ComputerTool
from computer_use_modal.tools.edit.edit import EditTool


@app.cls(image=image, allow_concurrent_inputs=10, secrets=[secrets], timeout=60 * 60)
class ComputerUseServer:
    @modal.enter()
    def init(self):
        logging.basicConfig(level=logging.INFO)

        self.client = Anthropic()

    @modal.method(is_generator=True)
    async def messages_create(
        self,
        request_id: str,
        user_messages: list[BetaMessageParam],
        max_tokens: int = 4096,
        model: str = "claude-3-5-sonnet-20241022",
    ) -> AsyncGenerator[BetaMessageParam | ToolResult, None]:
        manager = SandboxManager(request_id=request_id)
        messages = await Messages.from_request_id(request_id)
        await messages.add_user_messages(user_messages)

        tools = (
            ComputerTool(manager=manager),
            EditTool(manager=manager),
            BashTool(manager=manager),
        )

        while True:
            tool_runner = ToolCollection(tools=tools)
            response = self.client.beta.messages.create(
                max_tokens=max_tokens,
                messages=messages.messages,
                model=model,
                system=SYSTEM_PROMPT,
                tools=tool_runner.to_params(),
                betas=["computer-use-2024-10-22", "prompt-caching-2024-07-31"],
            )
            yield await messages.add_assistant_content(
                cast(list[BetaContentBlockParam], response.content)
            )
            for content_block in cast(list[BetaContentBlock], response.content):
                if content_block.type != "tool_use":
                    continue
                yield await tool_runner.run(
                    name=content_block.name,
                    tool_input=cast(dict, content_block.input),
                    tool_use_id=content_block.id,
                )
            if not tool_runner.results:
                return
            yield await messages.add_tool_result(
                [r.to_api() for r in tool_runner.results]
            )

    @modal.method()
    async def debug(self, request_id: str):
        manager = SandboxManager(request_id=request_id)
        return await manager.debug_urls.remote.aio()
