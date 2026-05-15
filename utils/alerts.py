import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import (EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO,
                    EMAIL_SMTP_HOST, EMAIL_SMTP_PORT,
                    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)


def enviar_alerta_email(cantidad: int, coords: list, informe: str = '') -> bool:
    """Send email alert using config variables. Returns True on success."""
    if not all([EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO]):
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'AEGIS-IMINT ALERTA: {cantidad} vehiculos detectados'
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO

        html = f"""<html><body>
        <h2 style="color:red;">ALERTA TACTICA — AEGIS-IMINT</h2>
        <table border="1">
          <tr><td><b>Vehiculos</b></td><td>{cantidad}</td></tr>
          <tr><td><b>Zona</b></td><td>{coords}</td></tr>
        </table>
        {'<h3>Informe LLM</h3><pre>' + informe + '</pre>' if informe else ''}
        </body></html>"""

        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(EMAIL_FROM, EMAIL_PASSWORD)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        return True
    except Exception as e:
        print(f"Error email: {e}")
        return False


def enviar_alerta_telegram(cantidad: int, coords: list, informe: str = '') -> bool:
    """Send Telegram alert using config variables. Returns True on success."""
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        return False
    try:
        msg = (f"*AEGIS-IMINT ALERTA*\n"
               f"*Vehiculos detectados:* {cantidad}\n"
               f"*Zona:* `{coords}`\n\n"
               + (informe[:500] if informe else ''))
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"Error Telegram: {e}")
        return False


def enviar_alertas(cantidad: int, coords: list, informe: str = '') -> dict:
    """Send all configured alerts, return status dict."""
    return {
        'email': enviar_alerta_email(cantidad, coords, informe),
        'telegram': enviar_alerta_telegram(cantidad, coords, informe),
    }
