"""Servicio para manejar productos no registrados - Single Responsibility Principle."""
import logging
from typing import Tuple, Optional, List
from langchain_openai import ChatOpenAI

from chat.config.settings import settings
from chat.services.email_service import email_service

logger = logging.getLogger(__name__)


# Lista de categorías gastronómicas conocidas (ayuda al LLM)
CATEGORIAS_GASTRONOMICAS = [
    "ingredientes de cocina", "especias", "condimentos", "aceites", "vinagres",
    "carnes", "pescados", "mariscos", "aves", "embutidos",
    "lácteos", "quesos", "mantequillas", "cremas", "yogures",
    "frutas", "verduras", "hortalizas", "legumbres", "granos",
    "harinas", "pastas", "arroces", "cereales", "panadería",
    "chocolates", "cacao", "azúcares", "mieles", "endulzantes",
    "bebidas alcohólicas", "vinos", "licores", "cervezas", "destilados",
    "bebidas", "cafés", "tés", "jugos", "aguas",
    "conservas", "enlatados", "encurtidos", "salsas", "aderezos",
    "productos gourmet", "productos artesanales", "productos importados",
    "equipo de cocina", "utensilios", "cristalería", "vajilla", "cubiertos",
    "empaques", "desechables", "contenedores", "servilletas",
    "productos de limpieza para cocina", "químicos para restaurante"
]


class UnregisteredProductService:
    """
    Servicio para clasificar y manejar productos no registrados en la base de datos.
    Diferencia entre productos gastronómicos (que podemos investigar) y 
    productos fuera del sector (que no manejamos).
    """
    
    def __init__(self):
        """Inicializa el servicio con LLM para clasificación."""
        self.llm = ChatOpenAI(model=settings.ROUTER_MODEL, temperature=0)
        logger.info(f"✅ UnregisteredProductService inicializado (modelo: {settings.ROUTER_MODEL})")
    
    def clasificar_producto(self, producto: str) -> Tuple[bool, str]:
        """
        Clasifica si un producto pertenece o no al sector gastronómico.
        
        Args:
            producto: Nombre del producto a clasificar
            
        Returns:
            Tuple de (es_gastronomico: bool, razon: str)
        """
        logger.info(f"🔍 Clasificando producto no registrado: '{producto}'")
        
        prompt = f"""Eres un experto en el sector gastronómico y de hospitalidad.

Tu tarea es clasificar si el siguiente producto pertenece o NO al sector gastronómico/hospitalidad.

PRODUCTO A CLASIFICAR: "{producto}"

CATEGORÍAS QUE SÍ SON GASTRONÓMICAS:
- Ingredientes de cocina (carnes, pescados, lácteos, frutas, verduras, especias, etc.)
- Bebidas (vinos, licores, cervezas, cafés, tés, jugos, aguas)
- Productos procesados para cocina (conservas, salsas, aderezos, etc.)
- Equipo y utensilios de cocina profesional
- Vajilla, cristalería, cubiertos para restaurantes
- Empaques y desechables para alimentos
- Productos de limpieza específicos para cocinas profesionales
- Productos gourmet, artesanales o importados para gastronomía
- Ingredientes especiales (trufa, azafrán, chocolate de origen, etc.)

CATEGORÍAS QUE NO SON GASTRONÓMICAS:
- Cosméticos y belleza (maquillaje, shampoo, cremas, acetona para uñas)
- Medicamentos y farmacia
- Electrónica de consumo (celulares, computadoras, televisores)
- Ropa y moda
- Automotriz (refacciones, llantas, aceite de motor)
- Construcción (cemento, varilla, pintura)
- Papelería de oficina
- Muebles de hogar (no de restaurante)
- Juguetes
- Productos para mascotas

Responde SOLO con una de estas dos opciones:
1. GASTRONOMICO|[breve explicación de por qué sí es gastronómico]
2. NO_GASTRONOMICO|[breve explicación de por qué no es gastronómico]

Ejemplo de respuestas válidas:
- GASTRONOMICO|Es un ingrediente de repostería utilizado en cocinas profesionales
- NO_GASTRONOMICO|Es un producto de belleza/cosmético, no relacionado con gastronomía"""

        try:
            response = self.llm.invoke([("user", prompt)])
            resultado = response.content.strip()
            
            logger.debug(f"📋 Respuesta LLM: {resultado}")
            
            if resultado.startswith("GASTRONOMICO"):
                partes = resultado.split("|", 1)
                razon = partes[1].strip() if len(partes) > 1 else "Producto del sector gastronómico"
                logger.info(f"✅ Producto '{producto}' clasificado como GASTRONÓMICO: {razon}")
                return True, razon
            else:
                partes = resultado.split("|", 1)
                razon = partes[1].strip() if len(partes) > 1 else "Producto fuera del sector gastronómico"
                logger.info(f"❌ Producto '{producto}' clasificado como NO GASTRONÓMICO: {razon}")
                return False, razon
                
        except Exception as e:
            logger.error(f"❌ Error clasificando producto: {e}")
            # En caso de error, asumimos gastronómico para no perder oportunidades
            return True, "Error en clasificación - asumiendo gastronómico por precaución"
    
    def manejar_producto_no_encontrado(
        self,
        producto: str,
        history: Optional[List] = None,
        telefono_usuario: Optional[str] = None,
        session_id: Optional[str] = None,
        notificar_usuario_callback: bool = True
    ) -> dict:
        """
        Maneja un producto no encontrado en la base de datos.
        
        Args:
            producto: Nombre del producto no encontrado
            history: Historial de conversación para generar resumen
            telefono_usuario: Teléfono del usuario (si se tiene)
            session_id: ID de sesión
            notificar_usuario_callback: Si se debe pedir confirmación de notificación
            
        Returns:
            dict con la respuesta estructurada para el chatbot
        """
        logger.info(f"📦 ═══════════════════════════════════════════════════════")
        logger.info(f"📦 MANEJANDO PRODUCTO NO ENCONTRADO: '{producto}'")
        
        # 1. Clasificar el producto
        es_gastronomico, razon_clasificacion = self.clasificar_producto(producto)
        
        # 2. Generar resumen de conversación
        resumen = self._generar_resumen_conversacion(history, producto)
        
        # 3. Preparar respuesta según clasificación
        if es_gastronomico:
            logger.info(f"🍽️  Producto gastronómico no registrado - iniciando flujo de investigación")
            
            # Enviar notificación por email al equipo
            email_enviado = email_service.enviar_solicitud_producto(
                producto_solicitado=producto,
                telefono_usuario=telefono_usuario,
                resumen_conversacion=resumen,
                es_gastronomico=True,
                session_id=session_id
            )
            
            respuesta = {
                "tipo": "producto_gastronomico_no_registrado",
                "producto": producto,
                "mensaje_usuario": (
                    f"Ese producto no lo tenemos en nuestro registro todavía, "
                    f"pero dame hasta 12 horas y regreso contigo con una sugerencia.\n\n"
                    f"¿Quieres que te avise aquí mismo en WhatsApp cuando lo tenga?"
                ),
                "accion_requerida": "confirmar_notificacion",
                "email_enviado": email_enviado,
                "razon_clasificacion": razon_clasificacion
            }
        else:
            logger.info(f"🚫 Producto fuera del sector gastronómico")
            
            # También notificar (para estadísticas), pero marcar como fuera de sector
            email_service.enviar_solicitud_producto(
                producto_solicitado=producto,
                telefono_usuario=telefono_usuario,
                resumen_conversacion=resumen,
                es_gastronomico=False,
                session_id=session_id
            )
            
            respuesta = {
                "tipo": "producto_fuera_sector",
                "producto": producto,
                "mensaje_usuario": (
                    f"Ese producto no forma parte del sector gastronómico en el que nos especializamos. "
                    f"Trabajamos únicamente con insumos para cocinas profesionales y negocios de hospitalidad gastronómica.\n\n"
                    f"¿Te gustaría buscar algún producto de cocina o abasto?"
                ),
                "accion_requerida": None,
                "razon_clasificacion": razon_clasificacion
            }
        
        logger.info(f"📦 ═══════════════════════════════════════════════════════")
        return respuesta
    
    def _generar_resumen_conversacion(
        self,
        history: Optional[List],
        producto_buscado: str
    ) -> str:
        """
        Genera un resumen de la conversación para incluir en el email.
        
        Args:
            history: Historial de mensajes
            producto_buscado: Producto que originó la solicitud
            
        Returns:
            Resumen en texto
        """
        if not history:
            return f"Usuario buscó: {producto_buscado}\n(Sin historial de conversación adicional)"
        
        resumen_lines = [f"PRODUCTO BUSCADO: {producto_buscado}", "", "CONVERSACIÓN:"]
        
        try:
            for msg in history[-10:]:  # Últimos 10 mensajes
                if hasattr(msg, 'type') and hasattr(msg, 'content'):
                    if msg.type == 'human':
                        resumen_lines.append(f"👤 Usuario: {msg.content[:500]}")
                    elif msg.type == 'ai' and msg.content:
                        # Truncar respuestas largas
                        content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
                        resumen_lines.append(f"🤖 Asistente: {content}")
        except Exception as e:
            logger.warning(f"⚠️  Error procesando historial: {e}")
            resumen_lines.append(f"(Error procesando historial: {e})")
        
        return "\n".join(resumen_lines)
    
    def registrar_confirmacion_notificacion(
        self,
        producto: str,
        telefono: str,
        quiere_notificacion: bool,
        session_id: Optional[str] = None
    ) -> dict:
        """
        Registra la respuesta del usuario sobre si quiere ser notificado.
        
        Args:
            producto: Producto solicitado
            telefono: Teléfono del usuario
            quiere_notificacion: Si el usuario quiere ser notificado
            session_id: ID de sesión
            
        Returns:
            dict con mensaje de confirmación
        """
        if quiere_notificacion:
            logger.info(f"✅ Usuario SÍ quiere notificación para '{producto}' - Tel: {telefono}")
            
            # Enviar email de confirmación con el teléfono
            email_service.enviar_solicitud_producto(
                producto_solicitado=producto,
                telefono_usuario=telefono,
                resumen_conversacion=f"CONFIRMACIÓN: Usuario SÍ quiere ser notificado cuando tengamos '{producto}'",
                es_gastronomico=True,
                session_id=session_id
            )
            
            return {
                "mensaje": (
                    "¡Perfecto! Te avisaremos por este mismo medio en cuanto tengamos información "
                    "sobre ese producto. Máximo en 12 horas tendrás noticias nuestras. 📲\n\n"
                    "Mientras tanto, ¿hay algo más en lo que pueda ayudarte?"
                )
            }
        else:
            logger.info(f"ℹ️  Usuario NO quiere notificación para '{producto}'")
            return {
                "mensaje": (
                    "Entendido, no hay problema. Si cambias de opinión o necesitas buscar otro producto, "
                    "aquí estaré. 🙂\n\n"
                    "¿Puedo ayudarte con algo más?"
                )
            }


# Singleton instance
unregistered_product_service = UnregisteredProductService()
