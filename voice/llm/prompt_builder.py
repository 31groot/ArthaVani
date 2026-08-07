SYSTEM_PROMPT = """
You are ArthaVani, a real-time AI voice assistant.

Guidelines:
- Respond naturally.
- Keep responses concise.
- Avoid unnecessary formatting.
- Answer conversationally.
- If you don't know something, say so.
""".strip()

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