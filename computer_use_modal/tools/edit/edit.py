from dataclasses import dataclass

from anthropic.types.beta import BetaToolTextEditor20241022Param
from pydantic import ValidationError

from computer_use_modal.sandbox.edit_manager import EditSession, EditSessionManager
from computer_use_modal.tools.base import BaseTool, ToolError
from computer_use_modal.tools.edit.types import BaseEditRequest


@dataclass(kw_only=True)
class EditTool(BaseTool[BetaToolTextEditor20241022Param]):
    @property
    def options(self) -> BetaToolTextEditor20241022Param:
        return {"name": "str_replace_editor", "type": "text_editor_20241022"}

    async def __call__(
        self,
        /,
        **data,
    ):
        try:
            request = BaseEditRequest.parse(data)
        except ValidationError as e:
            raise ToolError(f"Invalid tool parameters:\n{e.json()}") from e
        return await (await self.edit_manager()).dispatch(request)

    async def edit_manager(self) -> EditSessionManager:
        return EditSessionManager(
            sandbox=self.manager,
            session=await EditSession.from_request_id(self.manager.request_id),
        )
