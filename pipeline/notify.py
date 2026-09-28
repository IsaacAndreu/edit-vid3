"""Messages to the owner: email (SMTP, e.g. Gmail with an app password) and/or Telegram.

.env (all optional — whatever is configured is used, the rest is skipped silently):
  SMTP_HOST=smtp.gmail.com  SMTP_PORT=587  SMTP_USER=tu@gmail.com  SMTP_PASSWORD=<contraseña de aplicación>
  EMAIL_TO=tu@gmail.com     TELEGRAM_BOT_TOKEN=...  TELEGRAM_CHAT_ID=...
"""

from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path

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
