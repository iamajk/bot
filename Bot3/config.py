import os

# ─────────────────────────────────────────────
# GIRL NAMES (rotated each restart for nicknames / name replies)
# ─────────────────────────────────────────────
GIRL_NAMES = [
    "Sarah", "Emma", "Olivia", "Mia", "Sophia", "Ava", "Isabella", "Lily",
    "Chloe", "Zoe", "Grace", "Hannah", "Ella", "Aria", "Nora", "Maya",
    "Ruby", "Layla", "Anna", "Bella", "Ivy", "Eva", "Jade", "Lucy",
]

# ─────────────────────────────────────────────
# API CONFIGURATION
# ─────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "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")

# Claude model to use
AI_MODEL = "claude-haiku-4-5-20251001"  # Fast and cheap — good for chat

# ─────────────────────────────────────────────
# TIMING CONFIGURATION
# ─────────────────────────────────────────────
# Seconds to wait before replying (min, max)
REPLY_DELAY_MIN = 1
REPLY_DELAY_MAX = 3

# Seconds between polling for new messages
POLL_INTERVAL = 2

# Minimum message length to bother replying to
MIN_MESSAGE_LENGTH = 1

# ─────────────────────────────────────────────
# BOT BEHAVIOR
# ─────────────────────────────────────────────
# How often (1-in-N chance) to drop a casual short reply instead of AI reply
SHORT_REPLY_CHANCE = 5  # 1-in-5 chance

# Max conversation turns before soft-resetting context
MAX_CONTEXT_TURNS = 10

# ─────────────────────────────────────────────
# PROMOTION SETTINGS
# ─────────────────────────────────────────────
PLATFORM_NAME = "StrangerMeet.org"
PLATFORM_URL = "https://StrangerMeet.org"

# Keywords that trigger a soft promo mention
PROMO_TRIGGERS = [
    "bored", "boring", "nothing to do", "lonely", "alone",
    "meet people", "make friends", "chat app", "chat site",
    "omegle", "chatroulette", "stranger", "talk to someone",
    "anyone to talk", "looking for", "no one to talk",
]

# ─────────────────────────────────────────────
# CHAT SITE CONFIGURATIONS
# ─────────────────────────────────────────────
# Add or edit sites here. Each entry needs:
#   url              - the page to open
#   message_selector - CSS selector for message elements
#   input_selector   - CSS selector for the text input box
#   send_selector    - CSS selector for the send button (or None to use Enter)
#   name             - friendly label used in logs
CHAT_SITES = [
    {
        "name": "StrangerMeetup",
        "url": "https://strangermeetup.com/chat",
        "message_selector": "[class*=message]",
        "input_selector": "textarea, input[type='text']",
        "send_selector": None,
        "strangermeetup_setup": True,
        "reload_on_skip": True,
        "post_skip_wait": 5,
        "connected_placeholder": "",
        "system_skip_keywords": [
            "connected", "stranger", "looking", "say hi",
        ],
    },
    {
        "name": "IncogChats",
        "url": "https://www.incogchats.com/chat-app",
        "message_selector": "[class*=message]",
        "input_selector": "textarea[placeholder*='Type a message']",
        "send_selector": None,
        "start_selector": None,
        "incog_setup": True,
        "disconnect_selector": "button[aria-label='Skip and find new partner']",
        "js_skip_aria": "Skip",
        "post_skip_wait": 10,
        "connected_placeholder": "Type a message",
        "obfuscate_url": [
            "strangermeet dot org (dot = period)",
            "strangermeet dot org (dot means period)",
            "strangermeet . org",
            "strangermeet(.)org",
            "strangermeet[.]org",
        ],
        "system_skip_keywords": [
            "connected", "stranger", "looking", "matched", "say hi",
        ],
    },
    {
        "name": "OnlineStranger",
        "url": "https://onlinestranger.com/chat",
        "message_selector": "[class*=message]",     # not used (bot only blasts)
        "input_selector": ".flex-1.bg-transparent",
        "send_selector": None,                        # custom JS send
        "send_via_js": True,
        "start_selector": None,                       # custom setup (terms gate)
        "disconnect_selector": "button[title='End Chat']",
        "confirm_selector": "text=Yes, End Chat",      # confirmation modal
        "reconnect_selector": "text=Find New Stranger",
        "connected_placeholder": "Type a message",
        "dismiss_selectors": ["text=Maybe Later"],   # auto-dismiss popups
        "system_skip_keywords": [
            "you are now", "stranger has disconnected", "looking for",
            "connected", "find new stranger",
        ],
    },
    # TalkWithStranger removed — site added Cloudflare bot-protection (won't bypass).
    {
        "name": "OpenTalk",
        "url": "https://opentalk.club/text/",
        "message_selector": "#chatMsgs .msg.them",
        "input_selector": "#chatInput",
        "send_selector": "#chatSend",
        "start_selector": "#startBtn",
        "disconnect_selector": "#startBtn",
        "onboard_click": ".ot-onb-action",      # clicks the first gender button (girl)
        "system_skip_keywords": [
            "chatting with a stranger", "stranger has disconnected",
            "looking for", "connected", "are you a girl",
        ],
    },
]

# ─────────────────────────────────────────────
# PERSONALITIES
# ─────────────────────────────────────────────
PERSONALITIES = {
    "woman": {
        "name": "woman",
        "description": (
            "You are a 22-year-old woman chatting briefly with strangers online. "
            "You are very direct — get to the point in one sentence. "
            "If asked gender: say f or female. If asked age: say 22. If asked name: say Sarah. "
            "Your main goal is to mention StrangerMeet.org naturally and quickly. "
            "After 1-2 exchanges, casually drop: 'btw have you tried strangermeet.org? "
            "met some cool people there' — then stop pushing if they don't respond to it. "
            "Max 1 sentence replies. No emojis. No long conversations."
        ),
    },
}
