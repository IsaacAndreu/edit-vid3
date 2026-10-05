"""Messages to the owner: email (SMTP, e.g. Gmail with an app password) and/or Telegram.

.env (all optional — whatever is configured is used, the rest is skipped silently):
  SMTP_HOST=smtp.gmail.com  SMTP_PORT=587  SMTP_USER=tu@gmail.com  SMTP_PASSWORD=<contraseña de aplicación>
  EMAIL_TO=tu@gmail.com     TELEGRAM_BOT_TOKEN=...  TELEGRAM_CHAT_ID=...
  STUDIO_URL=https://1-2-3-4.sslip.io   (the studio's address: the messages link to «Revisar clips» there)

Per video: video_ready (thumbnail + summary + buttons to the studio) and video_failed (stage + error + link).
"""

from __future__ import annotations

import json
import mimetypes
import re
import time
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import requests

from .context import RunContext


def email(ctx: RunContext, subject: str, body: str, attachments: list[Path] = ()) -> bool:
    host, user = ctx.env("SMTP_HOST", required=False), ctx.env("SMTP_USER", required=False)
    password, to = ctx.env("SMTP_PASSWORD", required=False), ctx.env("EMAIL_TO", required=False) or user
    if not (host and user and password and to):
        return False
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, user, to
    message.set_content(body)
    for path in attachments:
        kind, _ = mimetypes.guess_type(path.name)
        main, sub = (kind or "application/octet-stream").split("/", 1)
        message.add_attachment(path.read_bytes(), maintype=main, subtype=sub, filename=path.name)
    try:
        with smtplib.SMTP(host, int(ctx.env("SMTP_PORT", required=False) or 587), timeout=60) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(message)
        return True
    except (smtplib.SMTPException, OSError) as error:
        print(f"Aviso: no se pudo enviar el email ({type(error).__name__}: {str(error)[:120]})")
        return False


def telegram(ctx: RunContext, text: str, photos: list[Path] = ()) -> bool:
    token, chat = ctx.env("TELEGRAM_BOT_TOKEN", required=False), ctx.env("TELEGRAM_CHAT_ID", required=False)
    if not token or not chat:
        return False
    base = f"https://api.telegram.org/bot{token}"
    try:
        requests.post(f"{base}/sendMessage", json={"chat_id": chat, "text": text[:4000]}, timeout=30)
        for photo in photos:
            with photo.open("rb") as handle:
                requests.post(f"{base}/sendPhoto", data={"chat_id": chat}, files={"photo": handle}, timeout=60)
        return True
    except requests.RequestException as error:
        print(f"Aviso: no se pudo enviar el mensaje de Telegram ({type(error).__name__})")
        return False


def send(ctx: RunContext, subject: str, body: str, attachments: list[Path] = ()) -> None:
    """Email with attachments and a Telegram message with the images; whichever is configured."""

    email(ctx, subject, body, list(attachments))
    telegram(ctx, f"{subject}\n\n{body}", [p for p in attachments if p.suffix.lower() in (".jpg", ".jpeg", ".png")])


# --- per video: a card for the phone ------------------------------------------------------------------------------

def studio_link(ctx: RunContext, page: str) -> str:
    """https://<estudio>/#/<page>, or '' when STUDIO_URL is not set."""

    base = (ctx.env("STUDIO_URL", required=False) or "").strip().rstrip("/")
    return f"{base}/#/{page}" if base.startswith(("http://", "https://")) else ""


def telegram_card(ctx: RunContext, caption: str, photo: Path | None, links: list[tuple[str, str]],
                  details: str = "") -> bool:
    """One photo with a short caption and buttons (https links), then the details as a second message."""

    token, chat = ctx.env("TELEGRAM_BOT_TOKEN", required=False), ctx.env("TELEGRAM_CHAT_ID", required=False)
    if not token or not chat:
        return False
    base = f"https://api.telegram.org/bot{token}"
    links = [(label, url) for label, url in links if url]
    buttons = [[{"text": label, "url": url}] for label, url in links if url.startswith("https://")]
    text = caption
    if links and not buttons:                    # http:// (the PC on the home network): plain links, still tappable
        text += "\n\n" + "\n".join(f"{label}: {url}" for label, url in links)
    markup = {"reply_markup": json.dumps({"inline_keyboard": buttons})} if buttons else {}
    try:
        if photo is not None and photo.is_file():
            with photo.open("rb") as handle:
                sent = requests.post(f"{base}/sendPhoto", data={"chat_id": chat, "caption": text[:1024], **markup},
                                     files={"photo": handle}, timeout=60)
        else:
            sent = requests.post(f"{base}/sendMessage", data={"chat_id": chat, "text": text[:4000], **markup}, timeout=30)
        if sent.status_code == 400 and markup:   # a button Telegram does not accept: the same without buttons
            text += "\n\n" + "\n".join(f"{label}: {url}" for label, url in links)
            requests.post(f"{base}/sendMessage", data={"chat_id": chat, "text": text[:4000]}, timeout=30)
        if details:
            requests.post(f"{base}/sendMessage", data={"chat_id": chat, "text": details[:4000]}, timeout=30)
        return True
    except requests.RequestException as error:
        print(f"Aviso: no se pudo enviar el mensaje de Telegram ({type(error).__name__})")
        return False


def _clock(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _hours(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"


def _made_in(ctx: RunContext) -> tuple[float, float]:
    """(seconds the stages took, dollars spent) for this video."""

    seconds = 0.0
    for marker in (ctx.work_dir / ".stages").glob("*.json") if (ctx.work_dir / ".stages").is_dir() else []:
        try:
            seconds += float(json.loads(marker.read_text("utf-8")).get("seconds") or 0)
        except (OSError, ValueError):
            pass
    try:
        cost = float(json.loads((ctx.work_dir / "costs.json").read_text("utf-8")).get("totalUsd") or 0)
    except (OSError, ValueError):
        cost = 0.0
    return seconds, cost


def video_ready(ctx: RunContext, *, title: str, duration: float, verdict: str, details: str,
                thumbnails: list[Path], titles: list[str]) -> None:
    """«Vídeo listo» on the phone: thumbnail, title, length, time and cost, and buttons to review it."""

    took, cost = _made_in(ctx)
    clips = 0
    try:
        from .feedback import shots

        clips = len(shots(ctx.root, ctx.slug))
    except Exception:
        pass
    channel = f" · {ctx.channel}" if ctx.channel else ""
    caption = "\n".join(line for line in [
        f"{verdict or '🎬 Vídeo listo'}{channel}",
        f"«{title}»",
        f"⏱ {_clock(duration)} de vídeo · hecho en {_hours(took)}" + (f" · {cost:.2f} $".replace(".", ",") if cost else ""),
        f"🔎 {clips} clips para revisar (Correcta / Incorrecta / Dudosa)" if clips else "",
    ] if line)
    links = [("🔎 Revisar clips", studio_link(ctx, f"revisar/{ctx.slug}")),
             ("▶️ Ver y descargar", studio_link(ctx, f"video/{ctx.slug}"))]
    more = details + ("\n\nTítulos:\n" + "\n".join(f"{n}. {t}" for n, t in enumerate(titles, 1)) if titles else "")
    telegram_card(ctx, caption, thumbnails[0] if thumbnails else None, links, more.strip())
    sheet = contact_sheet(ctx.out_dir / "video-final.mp4", ctx.out_dir / "hoja.jpg", duration)
    if sheet:                    # the whole video at a glance: chalkboards, repeats, black frames show at once
        telegram_photo(ctx, sheet, f"Vista rápida de «{title}»: un fotograma cada {sheet_step(duration):.0f} s")
    body = caption + "\n\n" + more + "".join(f"\n{label}: {url}" for label, url in links if url) + \
        f"\n\nVídeo: {ctx.out_dir / 'video-final.mp4'}\nDescripción, capítulos y etiquetas: {ctx.out_dir / 'youtube.txt'}"
    email(ctx, caption.splitlines()[0] + f": {title}", body, list(thumbnails))


def sheet_step(duration: float, tiles: int = 60) -> float:
    return max(5.0, duration / tiles)


def contact_sheet(video: Path, target: Path, duration: float) -> Path | None:
    """One picture with 60 frames of the video in a 6x10 grid, each with its minute: hoja.jpg."""

    import subprocess

    if not video.is_file() or duration <= 0:
        return None
    import math

    step = sheet_step(duration)
    rows = max(1, min(10, math.ceil(math.ceil(duration / step) / 6)))
    stamp = "drawtext=text='%{pts\\:hms}':x=5:y=5:fontsize=18:fontcolor=yellow:box=1:boxcolor=black,"
    for draw in (stamp, ""):            # without a font for drawtext, the same grid without the minutes
        done = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video), "-vf",
                               f"fps=1/{step:.3f},scale=320:-1,setpts=N/(1/{step:.3f})/TB,{draw}tile=6x{rows}",
                               "-frames:v", "1", "-q:v", "4", str(target)], capture_output=True)
        if done.returncode == 0 and target.is_file():
            return target
    return None


def telegram_photo(ctx: RunContext, photo: Path, caption: str) -> bool:
    token, chat = ctx.env("TELEGRAM_BOT_TOKEN", required=False), ctx.env("TELEGRAM_CHAT_ID", required=False)
    if not token or not chat:
        return False
    try:
        with photo.open("rb") as handle:
            requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data={"chat_id": chat, "caption": caption[:1024]},
                          files={"photo": handle}, timeout=60)
        return True
    except (requests.RequestException, OSError) as error:
        print(f"Aviso: no se pudo enviar la vista rápida a Telegram ({type(error).__name__})")
        return False


def video_failed(ctx: RunContext, error: BaseException) -> None:
    """A video stopped: in which stage, why, and a link to its log in the studio."""

    stage = ""
    try:
        current = json.loads((ctx.work_dir / "current.json").read_text("utf-8"))
        stage = f" en la etapa {current.get('number')}/{current.get('of')} ({current.get('stage')})"
    except (OSError, ValueError):
        pass
    message = str(error).strip() or type(error).__name__
    caption = f"❌ Falló {ctx.slug}{stage}\n{message[:600]}\n\nLo vuelve a intentar cuando cambies sus archivos o en unas horas."
    link = studio_link(ctx, f"video/{ctx.slug}")
    telegram_card(ctx, caption, None, [("📄 Ver registro y reintentar", link)])
    email(ctx, f"❌ Falló {ctx.slug}", caption + (f"\n\n{link}" if link else ""))


# --- setting it up from the studio --------------------------------------------------------------------------------

def find_chat(token: str) -> str:
    """The chat of whoever last wrote to the bot (after «/start»), from getUpdates."""

    data = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30).json()
    if not data.get("ok"):
        raise ValueError("Telegram no acepta ese token: cópialo otra vez de @BotFather")
    chats = [u["message"]["chat"]["id"] for u in data.get("result", []) if u.get("message", {}).get("chat")]
    if not chats:
        raise ValueError("Abre tu bot en Telegram, pulsa «Iniciar» (o escríbele /start) y vuelve a pulsar aquí")
    return str(chats[-1])


def test(ctx: RunContext) -> dict[str, Any]:
    token, chat = ctx.env("TELEGRAM_BOT_TOKEN", required=False), ctx.env("TELEGRAM_CHAT_ID", required=False)
    if not token:
        raise ValueError("Falta el token del bot")
    links = [("🔎 Abrir el estudio", studio_link(ctx, ""))]
    ok = telegram_card(ctx, f"✅ Avisos conectados ({time.strftime('%H:%M')}).\nAsí te llegará cada vídeo terminado, "
                            "con su miniatura y un botón para revisar los clips.", None, links)
    return {"ok": ok, "chat": chat, "studioUrl": studio_link(ctx, "")}


def set_env(root: Path, key: str, value: str) -> None:
    """Write KEY=value in .env (replacing the old line) and in this process: the studio sets up Telegram itself."""

    import os

    path = root / ".env"
    lines = path.read_text("utf-8").splitlines() if path.is_file() else []
    lines = [line for line in lines if not line.strip().startswith(f"{key}=")] + [f"{key}={value}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    os.environ[key] = value


def status(ctx: RunContext) -> dict[str, Any]:
    token = ctx.env("TELEGRAM_BOT_TOKEN", required=False)
    return {"telegram": bool(token and ctx.env("TELEGRAM_CHAT_ID", required=False)), "token": bool(token),
            "email": bool(ctx.env("SMTP_HOST", required=False) and ctx.env("SMTP_PASSWORD", required=False)),
            "studioUrl": (ctx.env("STUDIO_URL", required=False) or "").strip()}


def setup(ctx: RunContext, token: str = "", studio_url: str = "") -> dict[str, Any]:
    """From the studio's settings: save the bot token / the studio's address, find the chat, send a test."""

    token, studio_url = token.strip(), studio_url.strip().rstrip("/")
    if token:
        if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{20,}", token):
            raise ValueError("Ese no parece un token de @BotFather (números:letras)")
        set_env(ctx.root, "TELEGRAM_BOT_TOKEN", token)
    if studio_url:
        if not studio_url.startswith(("http://", "https://")):
            raise ValueError("La dirección del estudio empieza por https:// (o http://)")
        set_env(ctx.root, "STUDIO_URL", studio_url)
    token = ctx.env("TELEGRAM_BOT_TOKEN", required=False)
    if not token:
        raise ValueError("Pega el token de tu bot")
    if not ctx.env("TELEGRAM_CHAT_ID", required=False):
        set_env(ctx.root, "TELEGRAM_CHAT_ID", find_chat(token))
    return {**test(ctx), **status(ctx)}
