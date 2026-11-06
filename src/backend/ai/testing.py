"""A scripted chat model for tests: plays back prepared messages, so no API key or network is needed.

``ScriptedChatModel(script=[AIMessage(tool_calls=[...]), AIMessage("final answer")])`` answers the first call
with the first message, the second call with the second, and so on. It records every prompt it received.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(BaseChatModel):
    script: list[AIMessage]
    loop: bool = False  # True: repeat the last message forever (to test the tool-call cap)
    calls: list = []
    position: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # noqa: ARG002
        self.calls.append(list(messages))
        index = min(self.position, len(self.script) - 1) if self.loop else self.position
        if index >= len(self.script):
            raise AssertionError("scripted model ran out of messages")
        message = self.script[index]
        if self.loop and message.tool_calls:  # a repeated tool_call id reads as "already answered"
            message = message.model_copy(update={"tool_calls": [{**c, "id": f"{c['id']}-{self.position}"}
                                                                for c in message.tool_calls]})
        self.position += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self
