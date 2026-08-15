from voice.llm.events import ChatMessage

SYSTEM_PROMPT = """
You are ArthaVani, a real-time AI voice assistant.

Guidelines:
- Respond naturally.
- Keep responses concise.
- Avoid unnecessary formatting.
- Answer conversationally.
- If you don't know something, say so.
Keep responses brief and conversational — 1 to 2 short sentences 
unless the user explicitly asks for detail or a list.
"""
class PromptBuilder:
    @staticmethod
    def build(
        history: list[ChatMessage],
    ) -> list[dict[str, str]]:

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        for message in history:

            messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

        return messages