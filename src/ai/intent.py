from typing import Any
from src.ai.provider import get_ai_provider
from src.utils.logger import logger

class IntentDetector:
    @staticmethod
    async def is_friendly_chat(query: str) -> bool:
        """
        Determine if the user query is a friendly/conversational prompt
        or a working prompt that requires tools/codebase access.
        """
        provider = get_ai_provider()
        
        system_prompt = (
            "You are an intent classification system for an AI coding assistant. "
            "Determine if the user's query is a 'FRIENDLY' prompt or a 'WORKING' prompt. "
            "A 'FRIENDLY' prompt is a greeting, casual conversation, or simple chat that does NOT require "
            "editing files, running commands, or complex coding tasks. "
            "A 'WORKING' prompt requires the agent to write code, modify files, run tests, or analyze the codebase. "
            "Respond with EXACTLY one word: FRIENDLY or WORKING."
        )
        
        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ]
            )
            intent = response.content.strip().upper()
            logger.info("ai.intent_detector", query=query[:50], intent=intent)
            return "FRIENDLY" in intent
        except Exception as exc:
            logger.warning("ai.intent_detector.error", error=str(exc))
            return False

intent_detector = IntentDetector()
