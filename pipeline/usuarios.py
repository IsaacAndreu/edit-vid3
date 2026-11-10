"""People who share the studio: you (the WEB_PASSWORD, you see everything) and partners, each with a password of
their own and their channels. A partner sees and touches only their channels' videos (web.py: a closed list of
pages, everything else answers 403), and the spend page bills each person their month (gasto.py).

out/_usuarios.json: {"users": {name: {"salt", "hash", "channels": [...], "created"}}}. Only a salted PBKDF2 of
each password is kept, never the password. The cookie of a partner is signed with their hash too, so a new
password closes their open sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

FILE = "out/_usuarios.json"
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,23}$")
ROUNDS = 200_000
ADMIN = ""                       # who you are in the code: the studio's own password, no name


def _read(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    users = data.get("users") if isinstance(data, dict) else None
    return users if isinstance(users, dict) else {}


def _write(root: Path, users: dict[str, Any]) -> None:
    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"users": users}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ROUNDS).hex()


def listing(root: Path) -> list[dict[str, Any]]:
    """For the settings page: names and channels, never the hashes."""

    return [{"name": n, "channels": list(u.get("channels") or []), "created": u.get("created"),
             "telegram": bool(u.get("telegram")), "limits": limits_of(root, n)} for n, u in sorted(_read(root).items())]


def channels_of(root: Path, name: str) -> list[str]:
    return list((_read(root).get(name) or {}).get("channels") or [])


def owner_of(root: Path, channel: str) -> str:
    """Whose channel it is: a partner's name, or ADMIN ("") when no partner has it."""

    for name, user in _read(root).items():
        if channel and channel in (user.get("channels") or []):
            return name
    return ADMIN


def owners(root: Path) -> dict[str, str]:
    """channel → partner, for every channel a partner has."""

    return {c: name for name, user in _read(root).items() for c in (user.get("channels") or [])}


def save(root: Path, name: str, channels: list[str], password: str = "", admin_password: str = "") -> dict[str, Any]:
    """A partner made or changed: their channels and, when given, a new password (8 characters at least, and not the
    studio's own: the login tells people apart by their password). A channel belongs to one person at a time."""

    name = str(name or "").strip().lower()
    if not NAME.match(name):
        raise ValueError("El nombre: 2-24 letras minúsculas, números, - o _ (sin espacios)")
    users = _read(root)
    if name not in users and not password:
        raise ValueError("Ponle una contraseña")
    channels = sorted({str(c).strip() for c in channels if str(c).strip()})
    taken = {c: n for n, u in users.items() if n != name for c in (u.get("channels") or [])}
    clash = [c for c in channels if c in taken]
    if clash:
        raise ValueError(f"{', '.join(clash)} ya es de {taken[clash[0]]}")
    user = dict(users.get(name) or {"created": time.strftime("%Y-%m-%d")})
    if password:
        if len(password) < 8:
            raise ValueError("La contraseña: 8 caracteres como mínimo")
        if admin_password and hmac.compare_digest(password.encode(), admin_password.encode()):
            raise ValueError("Esa es tu contraseña: ponle otra")
        if any(n != name and find(root, password) == n for n in users):
            raise ValueError("Esa contraseña ya la usa otra persona: ponle otra")
        user["salt"] = secrets.token_hex(16)
        user["hash"] = _hash(password, user["salt"])
    user["channels"] = channels
    users[name] = user
    _write(root, users)
    return {"users": listing(root)}


def add_channel(root: Path, name: str, channel: str) -> None:
    """A channel the partner just made in the studio: theirs from the start."""

    users = _read(root)
    if name in users:
        users[name]["channels"] = sorted(set(users[name].get("channels") or []) | {channel})
        _write(root, users)


def limits_of(root: Path, name: str) -> dict[str, float]:
    """{daily_usd, proxy_gb_per_day} of a partner, set by you in Ajustes → Personas (0 = no cap of their own)."""

    raw = (_read(root).get(name) or {}).get("limits") or {}
    out = {}
    for key in ("daily_usd", "proxy_gb_per_day"):
        try:
            out[key] = max(0.0, float(raw.get(key) or 0))
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


def set_limits(root: Path, name: str, limits: dict[str, Any]) -> None:
    users = _read(root)
    if name not in users:
        raise ValueError("No existe esa persona")
    current = dict(users[name].get("limits") or {})
    for key in ("daily_usd", "proxy_gb_per_day"):
        if key in limits:
            current[key] = max(0.0, float(limits[key] or 0))
    users[name]["limits"] = current
    _write(root, users)


def telegram_of(root: Path, name: str) -> str:
    """The partner's Telegram chat (their videos' messages go there), or ""."""

    return str((_read(root).get(name) or {}).get("telegram") or "")


def link_code(root: Path, name: str) -> str:
    """A one-time code: the partner sends «/start <code>» to the bot and their chat is saved (bot.py)."""

    users = _read(root)
    if name not in users:
        raise ValueError("No existe esa persona")
    code = secrets.token_hex(4)
    users[name]["telegramCode"] = {"code": code, "at": time.time()}
    _write(root, users)
    return code


def link_chat(root: Path, code: str, chat: str) -> str | None:
    """«/start <code>» from a chat: whose code it is (30 minutes), their chat saved; None when it matches nobody."""

    users = _read(root)
    for name, user in users.items():
        pending = user.get("telegramCode") or {}
        if pending.get("code") and hmac.compare_digest(str(pending["code"]), code) and time.time() - float(pending.get("at") or 0) < 1800:
            user["telegram"] = str(chat)
            user.pop("telegramCode", None)
            _write(root, users)
            return name
    return None


def unlink_chat(root: Path, name: str) -> None:
    users = _read(root)
    if name in users:
        users[name].pop("telegram", None)
        _write(root, users)


def remove(root: Path, name: str) -> dict[str, Any]:
    users = _read(root)
    users.pop(str(name or ""), None)
    _write(root, users)
    return {"users": listing(root)}


def find(root: Path, password: str) -> str | None:
    """The partner whose password this is, or None."""

    for name, user in _read(root).items():
        if user.get("salt") and user.get("hash") and hmac.compare_digest(_hash(password, user["salt"]), user["hash"]):
            return name
    return None


def token(root: Path, secret: bytes, name: str, now: float | None = None) -> str:
    stamp = str(int(now if now is not None else time.time()))
    key = (_read(root).get(name) or {}).get("hash", "")
    return f"u.{name}.{stamp}." + hmac.new(secret, f"{name}.{stamp}.{key}".encode(), hashlib.sha256).hexdigest()


def check(root: Path, secret: bytes, value: str, days: int = 30) -> str | None:
    """The partner a cookie belongs to, when it is theirs, recent and signed with their current password."""

    parts = value.split(".")
    if len(parts) != 4 or parts[0] != "u" or not parts[2].isdigit() or time.time() - int(parts[2]) > days * 86400:
        return None
    name, stamp, sig = parts[1], parts[2], parts[3]
    user = _read(root).get(name)
    if not user or not user.get("hash"):
        return None
    good = hmac.new(secret, f"{name}.{stamp}.{user['hash']}".encode(), hashlib.sha256).hexdigest()
    return name if hmac.compare_digest(sig, good) else None
