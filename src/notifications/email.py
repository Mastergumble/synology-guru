"""Email notification service."""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass


@dataclass
class EmailConfig:
    """Email configuration."""

    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_addr: str
    to_addr: str
    use_tls: bool = True


class EmailNotifier:
    """Send notifications via email."""

    def __init__(self, config: EmailConfig) -> None:
        """Initialize email notifier."""
        self.config = config

    def send(self, subject: str, body_html: str, body_text: str | None = None) -> bool:
        """Send an email notification.

        Args:
            subject: Email subject
            body_html: HTML body content
            body_text: Plain text body (optional, derived from HTML if not provided)

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.from_addr
            msg["To"] = self.config.to_addr

            # Plain text version
            if body_text is None:
                # Simple HTML to text conversion
                import re
                body_text = re.sub(r'<[^>]+>', '', body_html)
                body_text = body_text.replace('&nbsp;', ' ')
                body_text = body_text.replace('&lt;', '<')
                body_text = body_text.replace('&gt;', '>')
                body_text = body_text.replace('&amp;', '&')

            part1 = MIMEText(body_text, "plain", "utf-8")
            part2 = MIMEText(body_html, "html", "utf-8")

            msg.attach(part1)
            msg.attach(part2)

            # Send email
            if self.config.use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                    server.starttls(context=context)
                    server.login(self.config.username, self.config.password)
                    server.sendmail(
                        self.config.from_addr,
                        self.config.to_addr,
                        msg.as_string()
                    )
            else:
                with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                    server.login(self.config.username, self.config.password)
                    server.sendmail(
                        self.config.from_addr,
                        self.config.to_addr,
                        msg.as_string()
                    )

            return True

        except Exception as e:
            print(f"Failed to send email: {e}")
            return False
