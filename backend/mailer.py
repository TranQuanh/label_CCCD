"""
mailer.py
=========
Gửi email qua SMTP (thư viện chuẩn `smtplib`, không cần cài thêm gói).

Cấu hình nằm trong `config.py` (SMTP_HOST/PORT/USER/PASSWORD). Chưa điền
SMTP_USER hoặc SMTP_PASSWORD → không gửi, chỉ in nội dung ra log (chế độ dev).

Hàm gửi được gọi qua FastAPI BackgroundTasks (sau khi đã trả response) nên
lỗi SMTP chỉ ghi log, không ném ra ngoài.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from html import escape as html_escape

from . import config

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(config.SMTP_USER and config.SMTP_PASSWORD and config.SMTP_HOST)


def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Gửi một email. Trả True nếu gửi được (hoặc đã in ra log ở chế độ dev)."""
    if not smtp_configured():
        logger.warning(
            "SMTP chưa cấu hình — KHÔNG gửi mail. Nội dung gửi tới %s:\n%s\n%s",
            to, subject, text,
        )
        return True

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((config.SMTP_FROM_NAME, config.SMTP_USER))
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    ctx = ssl.create_default_context()
    try:
        if config.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT,
                                  timeout=config.SMTP_TIMEOUT_SECONDS, context=ctx) as s:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT,
                              timeout=config.SMTP_TIMEOUT_SECONDS) as s:
                s.starttls(context=ctx)
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        logger.info("Đã gửi email '%s' tới %s", subject, to)
        return True
    except Exception as exc:  # noqa: BLE001 — chạy nền, chỉ ghi log
        logger.error("Gửi email tới %s thất bại: %s", to, exc)
        return False


def send_reset_code(to: str, name: str, code: str) -> None:
    """Email chứa mã OTP đặt lại mật khẩu."""
    ttl = config.RESET_CODE_TTL_MIN
    greeting = f"Xin chào {name}," if name else "Xin chào,"
    # full_name do người dùng tự nhập → escape trước khi chèn vào HTML.
    greeting_html = html_escape(greeting)
    text = (
        f"{greeting}\n\n"
        f"Mã đặt lại mật khẩu SmartID của bạn là: {code}\n"
        f"Mã có hiệu lực trong {ttl} phút và chỉ dùng được một lần.\n\n"
        "Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này. "
        "Mật khẩu hiện tại của bạn vẫn giữ nguyên.\n\n"
        "— SmartID"
    )
    html = f"""\
<div style="font-family:Arial,sans-serif;font-size:14px;color:#1d2333">
  <p>{greeting_html}</p>
  <p>Mã đặt lại mật khẩu SmartID của bạn là:</p>
  <p style="font-size:28px;font-weight:bold;letter-spacing:6px;color:#0b2a5b">{code}</p>
  <p>Mã có hiệu lực trong <b>{ttl} phút</b> và chỉ dùng được một lần.</p>
  <p style="color:#6b7385">Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này.
  Mật khẩu hiện tại của bạn vẫn giữ nguyên.</p>
  <p>— SmartID</p>
</div>"""
    send_email(to, f"[SmartID] Mã đặt lại mật khẩu: {code}", text, html)
