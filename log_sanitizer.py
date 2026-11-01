"""
mc_launcher.log_sanitizer - hides personal details in a Minecraft log before you post it publicly.

Hidden: your Windows/Linux/macOS user name in paths (and the name itself), the player name you pass in, player UUIDs,
access tokens and related launch arguments, bearer/JWT tokens, e-mail addresses and server IP:port addresses.
Version numbers (1.20.1, 47.4.10, ...) and everything else are left alone so the log stays useful.
"""
import getpass
import re

_USER_PATHS = [
    (re.compile(r"(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/\s\"']+"), r"\1<user>"),
    (re.compile(r"(/home/)[^/\s\"']+"), r"\1<user>"),
    (re.compile(r"(/Users/)[^/\s\"']+"), r"\1<user>"),
]
_ARGS = re.compile(r"(?i)(--(?:accessToken|uuid|username|xuid|clientId|userProperties|sessionId)(?:\s+|=))(\"[^\"]*\"|\S+)")
_SECRETS = [
    (re.compile(r"(?i)\b(access_?token|refresh_?token|session_?id|authorization)(\"?\s*[:=]\s*\"?)(?:Bearer\s+)?[A-Za-z0-9._\-+/=]{12,}"), r"\1\2<hidden>"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{12,}"), "Bearer <hidden>"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]*"), "<hidden-token>"),
]
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}\b")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_IP_PORT = re.compile(r"\b(?!(?:127\.0\.0\.1|0\.0\.0\.0|localhost)\b)(\d{1,3}(?:\.\d{1,3}){3}):\d{2,5}\b")


def sanitize(text: str, names=()) -> str:
    """names: extra words to hide, e.g. the Minecraft player name."""
    for rx, rep in _USER_PATHS:
        text = rx.sub(rep, text)
    text = _ARGS.sub(lambda m: m.group(1) + "<hidden>", text)
    for rx, rep in _SECRETS:
        text = rx.sub(rep, text)
    text = _UUID.sub("<uuid>", text)
    text = _EMAIL.sub("<email>", text)
    text = _IP_PORT.sub("<ip>:<port>", text)
    try:
        os_user = getpass.getuser()
    except Exception:
        os_user = ""
    for n, label in [(os_user, "<user>")] + [(n, "<player>") for n in names]:
        if n and len(n) >= 3:
            text = re.sub(r"(?i)(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", label, text)
    return text
