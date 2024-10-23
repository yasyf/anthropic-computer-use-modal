from typing import cast

import modal
from anthropic import Anthropic
from anthropic.types.beta import (
    BetaContentBlock,
    BetaContentBlockParam,
    BetaMessageParam,
)

from computer_use_modal.modal import app, image
from computer_use_modal.sandbox.sandbox_manager import SandboxManager
from computer_use_modal.server.messages import Messages
from computer_use_modal.server.prompts import SYSTEM_PROMPT
from computer_use_modal.tools.base import ToolCollection
from computer_use_modal.tools.bash import BashTool
from computer_use_modal.tools.computer.computer import ComputerTool
from computer_use_modal.tools.edit.edit import EditTool


@app.cls(image=image, allow_concurrent_inputs=10)
class ComputerUseServer:
    @modal.enter()
    def init(self):
        self.client = Anthropic()

    async def messages_create(
        self,
        request_id: str,
        user_messages: list[BetaMessageParam],
        max_tokens: int = 4096,
        model: str = "claude-3-5-sonnet-20241022",
    ):
        manager = SandboxManager(request_id=request_id)
        messages = await Messages.from_request_id(request_id)
        await messages.add_user_messages(user_messages)

        tools = ToolCollection(
            tools=(
                ComputerTool(manager=manager),
                EditTool(manager=manager),
                BashTool(manager=manager),
            )
        )
        while True:
            response = self.client.beta.messages.create(
                max_tokens=max_tokens,
                messages=messages.messages,
                model=model,
                system=SYSTEM_PROMPT,
                tools=tools.to_params(),
                betas=["computer-use-2024-10-22"],
            )
            await messages.add_assistant_content(
                cast(list[BetaContentBlockParam], response.content)
            )
            results = [
                (
                    await tools.run(
                        name=content_block.name,
                        tool_input=cast(dict, content_block.input),
                    )
                ).to_api(content_block.id)
                for content_block in cast(list[BetaContentBlock], response.content)
                if content_block.type == "tool_use"
            ]
            if not results:
                return
            await messages.add_tool_result(results)
