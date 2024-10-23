from dataclasses import dataclass

from anthropic.types.beta import BetaToolBash20241022Param

from computer_use_modal.sandbox.bash_manager import BashSession
from computer_use_modal.tools.base import BaseTool, ToolError, ToolResult


@dataclass(kw_only=True)
class BashTool(BaseTool[BetaToolBash20241022Param]):
    session: BashSession | None = None

    @property
    def options(self) -> BetaToolBash20241022Param:
        return {"name": "bash", "type": "bash_20241022"}

    async def __call__(
        self,
        /,
        command: str | None = None,
        restart: bool = False,
    ):
        if restart:
            if self.session is None:
                raise ToolError("No active bash session")
            await self.manager.end_bash_session.remote.aio(self.session)
            self.session = None
            return ToolResult(system="bash tool has been restarted")
        if not command:
            return ToolResult(system="no command provided")

        result = ToolResult()
        if self.session is None:
            self.session = await self.manager.start_bash_session.remote.aio()
            result += ToolResult(system="bash tool has been started")
        result += await self.manager.execute_bash_command.remote.aio(
            self.session, command
        )
        return result
