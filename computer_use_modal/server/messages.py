from dataclasses import dataclass
from typing import Self, cast

import modal
from anthropic.types import ToolResultBlockParam
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessageParam,
    BetaToolResultBlockParam,
)


MESSAGES = modal.Dict.from_name("messages", create_if_missing=True)


@dataclass(kw_only=True)
class Messages:
    CHUNK_SIZE: int = 10

    request_id: str
    _messages: list[BetaMessageParam]
    keep_n_images: int = 10

    @classmethod
    async def from_request_id(cls, request_id: str) -> Self:
        return await MESSAGES.get.aio(
            request_id, cls(request_id=request_id, _messages=[])
        )

    async def flush(self):
        self._filter_images()
        await MESSAGES.put.aio(self.request_id, self)

    @property
    def messages(self) -> tuple[BetaMessageParam, ...]:
        return tuple(self._messages)

    async def add_assistant_content(self, content: list[BetaContentBlockParam]):
        self._messages.append({"role": "assistant", "content": content})
        await self.flush()

    async def add_user_messages(self, messages: list[BetaMessageParam]):
        self._messages.extend(messages)
        await self.flush()

    async def add_tool_result(self, tool_results: list[BetaToolResultBlockParam]):
        self._messages.append({"content": tool_results, "role": "user"})
        await self.flush()

    @property
    def tool_results(self) -> list[ToolResultBlockParam]:
        return cast(
            list[ToolResultBlockParam],
            [
                item
                for message in self.messages
                for item in (
                    message["content"] if isinstance(message["content"], list) else []
                )
                if isinstance(item, dict) and item.get("type") == "tool_result"
            ],
        )

    def _filter_images(self):
        total_images = sum(
            1
            for tool_result in self.tool_results
            for content in tool_result.get("content", [])
            if isinstance(content, dict) and content.get("type") == "image"
        )

        if not (
            images_to_remove := (total_images - self.keep_n_images) % self.CHUNK_SIZE
        ):
            return

        while images_to_remove > 0:
            for res in self.tool_results:
                if not isinstance(contents := res.get("content"), list):
                    continue
                for content in contents.copy():
                    if not isinstance(content, dict) and content.get("type") == "image":
                        continue
                    contents.remove(content)
                    images_to_remove -= 1
                    if images_to_remove == 0:
                        return
