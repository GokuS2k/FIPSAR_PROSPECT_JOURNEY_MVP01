"""
email_sender.py
---------------
Composes and sends FIPSAR Intelligence report emails via SMTP.

Features:
  - Professional HTML email with FIPSAR branding
  - Inline chart images (Plotly figures → PNG via kaleido)
  - Markdown → HTML conversion for report body
  - Graceful fallback when kaleido is not installed (charts skipped)
  - SMTP with STARTTLS (Gmail / Office 365 compatible)

Called exclusively by the send_report_email tool in tools.py.
"""

from __future__ import annotations

import io
import logging
import re
import smtplib
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from config import email_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chart → PNG conversion (requires kaleido; graceful skip if absent)
# ---------------------------------------------------------------------------

def _fig_to_png(fig) -> bytes | None:
    """Convert a Plotly figure to PNG bytes. Returns None if kaleido unavailable."""
    try:
        buf = io.BytesIO()
        fig.write_image(buf, format="png", width=900, height=500, scale=1.5)
        buf.seek(0)
        return buf.read()
    except Exception as exc:
        logger.warning("Chart→PNG conversion failed (kaleido installed?): %s", exc)
        return None


# ---------------------------------------------------------------------------
# Markdown → HTML (lightweight, no external deps)
# ---------------------------------------------------------------------------

def _md_to_html(text: str) -> str:
    """
    Convert a subset of markdown to HTML for email rendering.
    Handles: headers, bold, tables, bullet lists, line breaks.
    """
    # Escape HTML entities first
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    lines = text.split("\n")
    html_lines: list[str] = []
    in_table = False
    in_list = False

    for line in lines:
        # --- Headers ---
        if line.startswith("#### "):
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append(f"<h4 style='color:#1a3a6b;margin:12px 0 4px'>{line[5:]}</h4>")
            continue
        if line.startswith("### "):
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append(f"<h3 style='color:#1a3a6b;margin:14px 0 6px'>{line[4:]}</h3>")
            continue
        if line.startswith("## "):
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append(f"<h2 style='color:#1a3a6b;border-bottom:1px solid #dde;padding-bottom:4px;margin:18px 0 8px'>{line[3:]}</h2>")
            continue
        if line.startswith("# "):
            if in_list: html_lines.append("</ul>"); in_list = False
            html_lines.append(f"<h1 style='color:#0d2a5e;margin:20px 0 10px'>{line[2:]}</h1>")
            continue

        # --- Markdown table rows ---
        if line.startswith("|"):
            if not in_table:
                html_lines.append("<table style='border-collapse:collapse;width:100%;margin:10px 0;font-size:13px'>")
                in_table = True
            cells = [c.strip() for c in line.strip("|").split("|")]
            # Separator row  (---|---|---)
            if all(re.match(r"^[-:]+$", c) for c in cells if c):
                continue
            is_header = not any(
                prev.strip().startswith("<th") for prev in html_lines[-3:]
            ) and in_table and html_lines[-1].startswith("<table")
            tag = "th" if is_header else "td"
            style = (
                "background:#1a3a6b;color:#fff;padding:7px 10px;text-align:left;font-weight:600"
                if tag == "th"
                else "padding:6px 10px;border-bottom:1px solid #e0e4f0"
            )
            row_html = "".join(f"<{tag} style='{style}'>{c}</{tag}>" for c in cells)
            html_lines.append(f"<tr>{row_html}</tr>")
            continue
        else:
            if in_table:
                html_lines.append("</table>")
                in_table = False

        # --- Bullet list ---
        if line.startswith("- ") or line.startswith("* "):
            if not in_list:
                html_lines.append("<ul style='margin:6px 0 6px 20px;padding:0'>")
                in_list = True
            item = line[2:]
            # bold inside list item
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
            html_lines.append(f"<li style='margin:3px 0'>{item}</li>")
            continue
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False

        # --- Empty line ---
        if not line.strip():
            html_lines.append("<br>")
            continue

        # --- Normal paragraph with inline bold/italic ---
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"\*(.+?)\*", r"<em>\1</em>", line)
        line = re.sub(r"`(.+?)`", r"<code style='background:#f0f2f8;padding:1px 4px;border-radius:3px'>\1</code>", line)
        html_lines.append(f"<p style='margin:4px 0'>{line}</p>")

    if in_table:
        html_lines.append("</table>")
    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


# ---------------------------------------------------------------------------
# Email builder
# ---------------------------------------------------------------------------

def build_email(
    subject: str,
    report_markdown: str,
    chart_figures: list | None = None,
) -> MIMEMultipart:
    """
    Build a MIME email with:
      - Plain-text fallback
      - Branded HTML body
      - Inline PNG chart images (if any charts provided and kaleido available)

    Returns a MIMEMultipart object ready to send.
    """
    chart_figures = chart_figures or []
    timestamp = datetime.now().strftime("%B %d, %Y  %I:%M %p")

    # --- Convert charts to PNG ---
    chart_pngs: list[tuple[str, bytes]] = []  # (cid, png_bytes)
    chart_html_parts: list[str] = []
    for i, fig in enumerate(chart_figures):
        png = _fig_to_png(fig)
        if png:
            cid = f"chart_{i}"
            chart_pngs.append((cid, png))
            chart_html_parts.append(
                f"""
                <div style='margin:20px 0;text-align:center'>
                    <img src='cid:{cid}' style='max-width:100%;border-radius:8px;
                         box-shadow:0 2px 8px rgba(0,0,0,0.15)' alt='Chart {i+1}'>
                </div>
                """
            )

    chart_note = ""
    if chart_figures and not chart_pngs:
        chart_note = (
            "<p style='color:#888;font-style:italic;font-size:12px'>"
            "[Charts available in the FIPSAR Intelligence UI — install kaleido for email image export]"
            "</p>"
        )

    # --- Build HTML body ---
    body_html = _md_to_html(report_markdown)
    charts_section = "\n".join(chart_html_parts) if chart_html_parts else chart_note

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{subject}</title></head>
<body style="margin:0;padding:0;background:#f4f6fb;font-family:Arial,Helvetica,sans-serif">

<!-- Wrapper -->
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6fb;padding:30px 0">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0"
       style="background:#ffffff;border-radius:10px;overflow:hidden;
              box-shadow:0 4px 20px rgba(0,0,0,0.10)">

  <!-- Header -->
  <tr>
    <td style="background:linear-gradient(135deg,#0d2a5e 0%,#1a4a9e 100%);
               padding:28px 36px;text-align:left">
      <div style="color:#ffffff;font-size:22px;font-weight:700;letter-spacing:0.5px">
        FIPSAR Intelligence
      </div>
      <div style="color:#a0c0ff;font-size:13px;margin-top:4px">
        Prospect Journey AI · Automated Report
      </div>
    </td>
  </tr>

  <!-- Subject banner -->
  <tr>
    <td style="background:#e8eef8;padding:14px 36px;
               border-left:4px solid #1a4a9e">
      <div style="font-size:17px;font-weight:700;color:#0d2a5e">{subject}</div>
      <div style="font-size:12px;color:#666;margin-top:3px">Generated: {timestamp}</div>
    </td>
  </tr>

  <!-- Body -->
  <tr>
    <td style="padding:28px 36px;color:#222;font-size:14px;line-height:1.7">
      {body_html}
      {charts_section}
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background:#f0f4fb;padding:18px 36px;border-top:1px solid #dde2f0">
      <div style="font-size:11px;color:#888;line-height:1.6">
        This report was generated automatically by the
        <strong>FIPSAR Prospect Journey Intelligence</strong> AI assistant.<br>
        Data source: Snowflake live query &nbsp;|&nbsp;
        AI: GPT-4o via LangGraph &nbsp;|&nbsp;
        {timestamp}
      </div>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body></html>"""

    # --- Plain text fallback ---
    plain = f"FIPSAR Intelligence Report\n{'='*50}\n{subject}\nGenerated: {timestamp}\n\n{report_markdown}"

    # --- Assemble MIME message ---
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = f"{email_config.from_name} <{email_config.from_address}>"
    msg["To"] = email_config.to_address

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain, "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)

    # Attach chart PNG images with Content-ID
    for cid, png_bytes in chart_pngs:
        img = MIMEImage(png_bytes, "png")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
        msg.attach(img)

    return msg


# ---------------------------------------------------------------------------
# SMTP sender
# ---------------------------------------------------------------------------

def send_email(
    subject: str,
    report_markdown: str,
    chart_figures: list | None = None,
) -> dict[str, Any]:
    """
    Build and send the HTML report email via SMTP.

    Returns a dict with:
        success  : bool
        to       : str
        subject  : str
        message  : str   — human-readable status for the agent to report back
        charts_attached : int
    """
    if not email_config.is_configured:
        return {
            "success": False,
            "message": (
                "Email credentials are not configured. "
                "Add EMAIL_SMTP_USER and EMAIL_SMTP_PASSWORD to the .env file."
            ),
            "to": email_config.to_address,
            "subject": subject,
            "charts_attached": 0,
        }

    chart_figures = chart_figures or []
    msg = build_email(subject, report_markdown, chart_figures)

    # Count how many charts actually rendered to PNG
    charts_attached = sum(
        1 for fig in chart_figures if _fig_to_png(fig) is not None
    )

    try:
        with smtplib.SMTP(email_config.smtp_host, email_config.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(email_config.smtp_user, email_config.smtp_password)
            server.sendmail(
                email_config.from_address or email_config.smtp_user,
                email_config.to_address,
                msg.as_string(),
            )

        logger.info(
            "Email sent — to=%s subject=%s charts=%d",
            email_config.to_address, subject, charts_attached,
        )
        return {
            "success": True,
            "to": email_config.to_address,
            "subject": subject,
            "charts_attached": charts_attached,
            "message": (
                f"Email successfully sent to {email_config.to_address}. "
                f"Subject: '{subject}'. "
                f"Charts embedded: {charts_attached}."
            ),
        }

    except smtplib.SMTPAuthenticationError as exc:
        # Give a precise, actionable message for the most common failure mode
        hint = ""
        if "your-sender@gmail.com" in email_config.smtp_user:
            hint = " EMAIL_SMTP_USER is still the placeholder — set it to your real Gmail address."
        elif "gmail" in email_config.smtp_host.lower():
            hint = (
                " For Gmail you must use a 16-character App Password, NOT your account password. "
                "Generate one at: Google Account → Security → 2-Step Verification → App Passwords."
            )
        msg_str = f"SMTP authentication failed.{hint} Raw error: {exc}"
        logger.error(msg_str)
        return {"success": False, "message": msg_str, "to": email_config.to_address,
                "subject": subject, "charts_attached": 0}

    except smtplib.SMTPConnectError as exc:
        msg_str = (
            f"Could not connect to {email_config.smtp_host}:{email_config.smtp_port}. "
            f"Check EMAIL_SMTP_HOST and EMAIL_SMTP_PORT. Raw error: {exc}"
        )
        logger.error(msg_str)
        return {"success": False, "message": msg_str, "to": email_config.to_address,
                "subject": subject, "charts_attached": 0}

    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return {"success": False, "message": f"Email send failed: {exc}",
                "to": email_config.to_address, "subject": subject, "charts_attached": 0}


# ---------------------------------------------------------------------------
# Connection tester (used by Streamlit sidebar Test button)
# ---------------------------------------------------------------------------

def test_email_connection() -> dict[str, Any]:
    """
    Attempt an SMTP login without sending any message.
    Returns {"success": bool, "message": str}.
    Used by the Streamlit sidebar 'Test Email' button.
    """
    if not email_config.is_configured:
        return {
            "success": False,
            "message": (
                "EMAIL_SMTP_USER and/or EMAIL_SMTP_PASSWORD are not set in .env. "
                "Add them and restart the app."
            ),
        }

    if "your-sender@gmail.com" in email_config.smtp_user:
        return {
            "success": False,
            "message": (
                "EMAIL_SMTP_USER is still the placeholder value 'your-sender@gmail.com'. "
                "Replace it with your real Gmail address in .env and restart the app."
            ),
        }

    try:
        with smtplib.SMTP(email_config.smtp_host, email_config.smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(email_config.smtp_user, email_config.smtp_password)
        return {
            "success": True,
            "message": (
                f"SMTP login successful. Ready to send from {email_config.smtp_user} "
                f"to {email_config.to_address}."
            ),
        }

    except smtplib.SMTPAuthenticationError:
        gmail_hint = (
            " For Gmail: use a 16-character App Password (Google Account → Security → "
            "2-Step Verification → App Passwords), NOT your regular Gmail password."
            if "gmail" in email_config.smtp_host.lower() else ""
        )
        return {
            "success": False,
            "message": f"Authentication failed for {email_config.smtp_user}.{gmail_hint}",
        }

    except Exception as exc:
        return {"success": False, "message": f"Connection failed: {exc}"}
