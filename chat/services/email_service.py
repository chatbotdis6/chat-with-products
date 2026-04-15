"""Servicio de envío de emails - Single Responsibility Principle."""
import logging
import re
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

from chat.config.settings import settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Servicio para envío de notificaciones por email.
    Soporta SendGrid (preferido) o SMTP básico como fallback.
    """
    
    def __init__(self):
        """Inicializa el servicio de email."""
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("EMAIL_FROM", "noreply@zabukan.com")
        self.buzon_quejas = settings.BUZON_QUEJAS
        
        # Detectar método disponible
        if self.sendgrid_api_key:
            self.method = "sendgrid"
            logger.info("📧 EmailService: Usando SendGrid")
        elif self.smtp_user and self.smtp_password:
            self.method = "smtp"
            logger.info("📧 EmailService: Usando SMTP")
        else:
            self.method = "log_only"
            logger.warning("📧 EmailService: Sin credenciales configuradas - solo logging")
    
    def enviar_solicitud_producto(
        self,
        producto_solicitado: str,
        telefono_usuario: Optional[str],
        resumen_conversacion: str,
        es_gastronomico: bool = True,
        session_id: Optional[str] = None
    ) -> bool:
        """
        Envía notificación de solicitud de producto no registrado.
        
        Args:
            producto_solicitado: Nombre del producto que el usuario busca
            telefono_usuario: Teléfono del usuario (si lo proporcionó)
            resumen_conversacion: Resumen de la conversación con el usuario
            es_gastronomico: True si el producto es del sector gastronómico
            session_id: ID de sesión para tracking
            
        Returns:
            True si se envió correctamente, False en caso contrario
        """
        timestamp = datetime.now().strftime("%d/%m/%Y a las %H:%M hrs")
        
        # Limpiar markdown del resumen para email
        resumen_limpio = self._limpiar_markdown(resumen_conversacion)
        
        # Construir asunto
        if es_gastronomico:
            asunto = f"Nuevo producto solicitado: {producto_solicitado}"
        else:
            asunto = f"Consulta fuera de catálogo: {producto_solicitado}"
        
        # Formatear teléfono
        phone_html = self._format_phone_html(telefono_usuario)
        phone_text = self._format_phone_text(telefono_usuario)
        
        # ── HTML ──
        if es_gastronomico:
            header_bg = "#1B5E20"
            header_text = "Producto solicitado — Pendiente de investigación"
            accion_html = f"""
            <div style="background-color: #E8F5E9; border-left: 4px solid #2E7D32; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <p style="margin: 0 0 8px; font-weight: 600; color: #1B5E20;">Acción requerida</p>
                <p style="margin: 0; color: #333;">Investigar disponibilidad con proveedores y contactar al cliente en un plazo máximo de 12 horas.</p>
            </div>"""
        else:
            header_bg = "#B71C1C"
            header_text = "Consulta fuera del sector gastronómico"
            accion_html = f"""
            <div style="background-color: #FFF3E0; border-left: 4px solid #E65100; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <p style="margin: 0 0 8px; font-weight: 600; color: #E65100;">Solo informativo</p>
                <p style="margin: 0; color: #333;">El usuario solicitó un producto que no pertenece al sector gastronómico. No se requiere acción, se registra para estadísticas.</p>
            </div>"""
        
        cuerpo_html = f"""
        <html>
        <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
                
                <!-- Header -->
                <div style="background-color: {header_bg}; padding: 24px 32px;">
                    <h1 style="margin: 0; color: #ffffff; font-size: 20px; font-weight: 600;">
                        The Hap &amp; D Company
                    </h1>
                    <p style="margin: 8px 0 0; color: rgba(255,255,255,0.85); font-size: 14px;">
                        {header_text}
                    </p>
                </div>
                
                <!-- Body -->
                <div style="padding: 32px;">
                    
                    <!-- Datos principales -->
                    <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px;">
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #eee; color: #666; width: 160px; vertical-align: top;">Producto</td>
                            <td style="padding: 12px 0; border-bottom: 1px solid #eee; font-weight: 600; color: #111;">{producto_solicitado}</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #eee; color: #666; vertical-align: top;">Cliente</td>
                            <td style="padding: 12px 0; border-bottom: 1px solid #eee;">{phone_html}</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #eee; color: #666; vertical-align: top;">Fecha</td>
                            <td style="padding: 12px 0; border-bottom: 1px solid #eee; color: #111;">{timestamp}</td>
                        </tr>
                    </table>
                    
                    {accion_html}
                    
                    <!-- Conversación -->
                    <p style="font-weight: 600; color: #333; margin: 24px 0 12px; font-size: 15px;">Conversación con el cliente</p>
                    <div style="background-color: #FAFAFA; padding: 16px 20px; border-radius: 6px; border: 1px solid #E0E0E0; font-size: 14px; line-height: 1.7; color: #444;">
{resumen_limpio}
                    </div>
                    
                </div>
                
                <!-- Footer -->
                <div style="background-color: #FAFAFA; padding: 16px 32px; border-top: 1px solid #eee;">
                    <p style="margin: 0; color: #999; font-size: 12px;">
                        Notificación automática del asistente virtual — The Hap &amp; D Company
                    </p>
                </div>
                
            </div>
        </body>
        </html>
        """
        
        # ── Texto plano (fallback) ──
        if es_gastronomico:
            accion_texto = "ACCIÓN REQUERIDA: Investigar disponibilidad y contactar al cliente en máximo 12 horas."
        else:
            accion_texto = "Solo informativo — producto fuera del sector gastronómico."
        
        cuerpo_texto = f"""
The Hap & D Company — {header_text}
{'='*50}

Producto: {producto_solicitado}
Cliente: {phone_text}
Fecha: {timestamp}

{accion_texto}

Conversación:
{'-'*30}
{resumen_limpio}
{'-'*30}
        """
        
        return self._enviar_email(
            destinatario=self.buzon_quejas,
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            cuerpo_texto=cuerpo_texto
        )
    
    @staticmethod
    def _limpiar_markdown(texto: str) -> str:
        """Remove markdown artifacts so the email body reads cleanly."""
        # **bold** → bold
        texto = re.sub(r'\*\*(.+?)\*\*', r'\1', texto)
        # *italic* → italic
        texto = re.sub(r'\*(.+?)\*', r'\1', texto)
        # [text](url) → text (url)
        texto = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', texto)
        # Emoji removal (keep basic punctuation)
        texto = re.sub(
            r'[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0001FA00-\U0001FA6F'
            r'\U0001FA70-\U0001FAFF\U00002600-\U000026FF]+', '', texto
        )
        # Collapse multiple blank lines
        texto = re.sub(r'\n{3,}', '\n\n', texto)
        return texto.strip()

    def _format_phone_html(self, phone: Optional[str]) -> str:
        """
        Format phone number as clickeable WhatsApp link for the email.
        
        If the phone comes from Twilio it looks like 'whatsapp:+5215512345678'.
        We strip the prefix and create a wa.me link so the team can reply directly.
        """
        if not phone:
            return '<span style="color: #999;">No proporcionado</span>'
        
        # Strip whatsapp: prefix if present
        clean = phone.replace("whatsapp:", "").strip()
        # Remove any non-digit except leading +
        digits = clean.lstrip("+")
        
        return (
            f'{clean} &nbsp;&nbsp; '
            f'<a href="https://wa.me/{digits}" '
            f'style="background-color: #25D366; color: white; padding: 5px 14px; '
            f'border-radius: 4px; text-decoration: none; font-size: 13px; font-weight: 500;">'
            f'Responder por WhatsApp</a>'
        )

    @staticmethod
    def _format_phone_text(phone: Optional[str]) -> str:
        """Format phone for plain-text email fallback."""
        if not phone:
            return "No proporcionado"
        clean = phone.replace("whatsapp:", "").strip()
        digits = clean.lstrip("+")
        return f"{clean}  —  https://wa.me/{digits}"

    def _enviar_email(
        self,
        destinatario: str,
        asunto: str,
        cuerpo_html: str,
        cuerpo_texto: str
    ) -> bool:
        """
        Envía un email usando el método configurado.
        
        Args:
            destinatario: Email del destinatario
            asunto: Asunto del email
            cuerpo_html: Contenido HTML
            cuerpo_texto: Contenido texto plano (fallback)
            
        Returns:
            True si se envió correctamente
        """
        logger.info(f"📧 Enviando email a: {destinatario}")
        logger.info(f"📧 Asunto: {asunto}")
        
        if self.method == "sendgrid":
            return self._enviar_sendgrid(destinatario, asunto, cuerpo_html, cuerpo_texto)
        elif self.method == "smtp":
            return self._enviar_smtp(destinatario, asunto, cuerpo_html, cuerpo_texto)
        else:
            # Log only mode
            logger.warning("📧 [LOG ONLY] Email no enviado - sin credenciales configuradas")
            logger.info(f"📧 [LOG ONLY] Destinatario: {destinatario}")
            logger.info(f"📧 [LOG ONLY] Asunto: {asunto}")
            logger.info(f"📧 [LOG ONLY] Contenido:\n{cuerpo_texto}")
            return True  # Retorna True para no bloquear el flujo
    
    def _enviar_sendgrid(
        self,
        destinatario: str,
        asunto: str,
        cuerpo_html: str,
        cuerpo_texto: str
    ) -> bool:
        """Envía email usando SendGrid API."""
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Email, To, Content
            
            sg = sendgrid.SendGridAPIClient(api_key=self.sendgrid_api_key)
            
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(destinatario),
                subject=asunto,
                html_content=Content("text/html", cuerpo_html)
            )
            
            response = sg.send(message)
            
            if response.status_code in (200, 201, 202):
                logger.info(f"✅ Email enviado via SendGrid (status: {response.status_code})")
                return True
            else:
                logger.error(f"❌ Error SendGrid: status {response.status_code}")
                return False
                
        except ImportError:
            logger.error("❌ sendgrid no instalado. Ejecuta: pip install sendgrid")
            return False
        except Exception as e:
            logger.error(f"❌ Error enviando email via SendGrid: {e}")
            return False
    
    def _enviar_smtp(
        self,
        destinatario: str,
        asunto: str,
        cuerpo_html: str,
        cuerpo_texto: str
    ) -> bool:
        """Envía email usando SMTP."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = asunto
            msg["From"] = self.from_email
            msg["To"] = destinatario
            
            # Adjuntar versión texto y HTML
            part1 = MIMEText(cuerpo_texto, "plain")
            part2 = MIMEText(cuerpo_html, "html")
            msg.attach(part1)
            msg.attach(part2)
            
            # Conectar y enviar
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, destinatario, msg.as_string())
            
            logger.info(f"✅ Email enviado via SMTP")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error enviando email via SMTP: {e}")
            return False


# Singleton instance
email_service = EmailService()
