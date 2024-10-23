import logging
from dataclasses import dataclass
from typing import Self, cast

import modal
from anthropic.types.beta import (
    BetaCacheControlEphemeralParam,
    BetaContentBlockParam,
    BetaMessageParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)

MESSAGES = modal.Dict.from_name("messages", create_if_missing=True)

logger = logging.getLogger(__name__)


@dataclass(kw_only=True)
class Messages:
    CHUNK_SIZE: int = 10
    MAX_CACHE_CONTROL: int = 4

    request_id: str
    _messages: list[BetaMessageParam]
    keep_n_images: int = 10

    @classmethod
    async def from_request_id(cls, request_id: str) -> Self:
        return await MESSAGES.get.aio(
            request_id, cls(request_id=request_id, _messages=[])
        )

    async def flush(self):
        self._filter_cache_control()
        self._filter_images()
        await MESSAGES.put.aio(self.request_id, self)

    @property
    def messages(self) -> tuple[BetaMessageParam, ...]:
        return tuple(self._messages)

    async def add_assistant_content(self, content: list[BetaContentBlockParam]):
        logger.info(f"AI said: {content}")
        self._messages.append(
            msg := {"role": "assistant", "content": content},
        )
        await self.flush()
        return msg

    async def add_user_messages(self, messages: list[BetaMessageParam]):
        logger.info(f"User said: {messages}")
        self._messages.extend(messages)
        await self.flush()

    async def add_tool_result(self, tool_results: list[BetaToolResultBlockParam]):
        self._messages.append(
            msg := {"content": tool_results, "role": "user"},
        )
        self.tool_results[-1]["cache_control"] = cast(
            BetaCacheControlEphemeralParam, {"type": "ephemeral"}
        )
        await self.flush()
        return msg

    @property
    def tool_results(self) -> list[BetaToolUseBlockParam]:
        return cast(
            list[BetaToolUseBlockParam],
            [
                item
                for message in self._messages
                for item in (
                    message["content"] if isinstance(message["content"], list) else []
                )
                if isinstance(item, dict) and item.get("type") == "tool_result"
            ],
        )

    def _filter_cache_control(self):
        total_cache_control = sum(
            1 for tool_result in self.tool_results if "cache_control" in tool_result
        )
        if (to_remove := total_cache_control - self.MAX_CACHE_CONTROL) <= 0:
            return
        while to_remove > 0:
            for tool_result in self.tool_results:
                if "cache_control" not in tool_result:
                    continue
                tool_result.pop("cache_control")
                to_remove -= 1
                if to_remove == 0:
                    return

    def _filter_images(self):
        total_images = sum(
            1
            for tool_result in self.tool_results
            for content in tool_result.get("content", [])
            if isinstance(content, dict) and content.get("type") == "image"
        )

        if total_images <= self.keep_n_images:
            return
        if not (
            images_to_remove := (total_images - self.keep_n_images) % self.CHUNK_SIZE
        ):
            return

        logger.info(f"Removing {images_to_remove} images")

        while images_to_remove > 0:
            for res in self.tool_results:
                if not isinstance(contents := res.get("content"), list):
                    continue
                for content in contents.copy():
                    if not (
                        isinstance(content, dict) and content.get("type") == "image"
                    ):
                        continue
                    contents.remove(content)
                    images_to_remove -= 1
                    if images_to_remove == 0:
                        return
