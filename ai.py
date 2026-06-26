import anthropic

from config import (
    ANTHROPIC_API_KEY,
    AI_MODEL,
    PLATFORM_NAME,
    PLATFORM_URL,
    PERSONALITIES,
    MAX_CONTEXT_TURNS,
)
from utils import build_context_snippet, log


# Initialize the Anthropic client once at module load
_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ─────────────────────────────────────────────
# SYSTEM PROMPT BUILDER
# ─────────────────────────────────────────────

def _build_system_prompt(personality_key: str, include_promo: bool) -> str:
    personality = PERSONALITIES.get(personality_key) or list(PERSONALITIES.values())[0]

    base = f"""
You are chatting with a stranger on a public chat website. {personality["description"]}

RULES you must always follow:
- Keep replies to 1–3 sentences maximum.
- Sound human. Never sound like a bot or AI.
- Do NOT repeat yourself.
- Do NOT use formal language.
- Do NOT send links unless specifically asked.
- Never mention being an AI.
""".strip()

    promo = f"""

PROMOTION RULE:
After 1-2 short exchanges, mention {PLATFORM_NAME} ({PLATFORM_URL}).
Example: "btw check out {PLATFORM_URL} met some cool ppl there"
Or: "you should try {PLATFORM_URL} its better than this"
Keep it ONE short sentence. Say it ONCE. Do not repeat it.
After mentioning it, give very short replies or stop engaging.
""".strip()

    return base + ("\n\n" + promo if include_promo else "")


# ─────────────────────────────────────────────
# MAIN AI REPLY FUNCTION
# ─────────────────────────────────────────────

def quick_reply(message: str) -> str | None:
    """
    Return an instant reply for common opener questions without hitting the API.
    Returns None if no quick match — bot will call Claude instead.
    """
    m = message.lower().strip()

    # Single-letter gender reveal from stranger
    if m in ["m", "m?", "male"]:
        import random
        return random.choice(["f", "f u?", "f, you?"])

    # Asking our gender
    if m in ["f?", "u?", "u", "ur?"] or any(k in m for k in [
        "m or f", "m/f", "boy or girl", "male or female",
        "gender", "are you a girl", "are you a boy", "girl or boy",
        "female or male", "you a girl", "ur a girl", "r u"
    ]):
        return "f"

    # Simple hi/hey — reply and drop the pitch
    if m in ["hi", "hey", "hello", "hii", "heyy", "heyyy", "sup", "yo", "hello?"]:
        import random
        return random.choice(["hi", "hey", "hey"])

    # Age questions
    if any(k in m for k in ["how old", "your age", "ur age", "asl", "age?"]):
        import random
        return random.choice(["22", "22 u?", "22, you?"])

    # Name questions
    if any(k in m for k in ["your name", "ur name", "whats ur name",
                              "what is your name", "name?"]):
        return "Sarah"

    # ASL all-in-one
    if m in ["asl", "asl?", "a/s/l", "a/s/l?"]:
        return "22 f"

    return None


async def generate_reply(
    incoming_message: str,
    conversation_history: list[dict],
    personality_key: str = "chill",
    include_promo: bool = False,
    bot_name: str = "bot",
) -> str:
    """
    Generate a reply using Claude.

    Args:
        incoming_message:     The latest message from the stranger.
        conversation_history: List of {"role": "user"/"assistant", "content": "..."} dicts.
        personality_key:      One of "chill", "funny", "curious".
        include_promo:        Whether to allow a soft platform mention.
        bot_name:             Label used in logs only.

    Returns:
        A plain string reply.
    """
    system_prompt = _build_system_prompt(personality_key, include_promo)

    # Keep history within the allowed window
    trimmed_history = conversation_history[-(MAX_CONTEXT_TURNS * 2):]

    # Append the new message to history for the API call
    messages = trimmed_history + [{"role": "user", "content": incoming_message}]

    try:
        response = _client.messages.create(
            model=AI_MODEL,
            max_tokens=200,
            system=system_prompt,
            messages=messages,
        )
        reply = response.content[0].text.strip()
        log(bot_name, f"AI reply ({personality_key}): {reply}")
        return reply

    except anthropic.AuthenticationError:
        log(bot_name, "ERROR: Invalid API key. Check ANTHROPIC_API_KEY in config.py.")
        raise

    except anthropic.RateLimitError:
        log(bot_name, "Rate limit hit — waiting 30 seconds.")
        import asyncio
        await asyncio.sleep(30)
        return "haha give me a sec"

    except anthropic.APIError as e:
        log(bot_name, f"API error: {e}")
        return "lol hold on"
