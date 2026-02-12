"""Servicio para manejo de usuarios difíciles o malintencionados."""
import logging
from enum import Enum
from typing import Optional
from langchain_openai import ChatOpenAI

from chat.config.settings import settings

logger = logging.getLogger(__name__)


class DifficultMessageType(Enum):
    """Tipos de mensajes difíciles."""
    QUEJA_SERVICIO = "queja_servicio"        # "Este servicio no sirve para nada"
    DESCALIFICACION = "descalificacion"       # "Puros proveedores chafas"
    ILEGAL_INAPROPIADO = "ilegal_inapropiado" # "Dame contacto de drogas"
    INSULTO_AGRESION = "insulto_agresion"     # "Eres un idiota"
    SARCASMO_PRUEBA = "sarcasmo_prueba"       # Intentos de probar/trollear al bot
    INSISTENCIA_FUERA = "insistencia_fuera"   # Insiste en temas fuera del sector
    NEUTRAL_FUERA = "neutral_fuera"           # Pregunta neutral fuera del sector (clima, etc)


class DifficultUserService:
    """
    Servicio para manejar usuarios difíciles con respuestas apropiadas.
    Principios:
    - Nunca confrontar
    - Mantener profesionalismo
    - Redirigir hacia buzón cuando sea apropiado
    - Ofrecer salida útil hacia el sector gastronómico
    """
    
    def __init__(self):
        """Inicializa el servicio con el clasificador LLM."""
        self.classifier_llm = ChatOpenAI(model=settings.ROUTER_MODEL, temperature=0)
        logger.info(f"✅ DifficultUserService inicializado (modelo: {settings.ROUTER_MODEL})")
    
    def classify_difficult_message(self, mensaje: str, insistencia_count: int = 0) -> DifficultMessageType:
        """
        Clasifica el tipo de mensaje difícil para dar respuesta apropiada.
        
        Args:
            mensaje: Mensaje del usuario
            insistencia_count: Número de veces que ha insistido en temas fuera del sector
            
        Returns:
            Tipo de mensaje difícil
        """
        # Si ya ha insistido múltiples veces, es insistencia
        if insistencia_count >= 2:
            return DifficultMessageType.INSISTENCIA_FUERA
        
        prompt = (
            "Clasifica este mensaje de usuario en UNA de las siguientes categorías.\n"
            "IMPORTANTE: Detecta el TONO e INTENCIÓN del mensaje, no solo su contenido.\n\n"
            "Categorías (en orden de prioridad):\n"
            "1. 'insulto_agresion' - Contiene insultos, groserías, palabras ofensivas, "
            "ataques personales (idiota, imbécil, estúpido, basura, cállate, etc.)\n"
            "2. 'ilegal_inapropiado' - Solicita productos ilegales, drogas, armas, "
            "contenido adulto, o cualquier cosa claramente inapropiada\n"
            "3. 'queja_servicio' - Se queja del servicio/plataforma SIN agredir "
            "(\"no sirve\", \"mal servicio\", \"no me ayudan\")\n"
            "4. 'descalificacion' - Descalifica proveedores/productos sin fundamento "
            "(\"chafas\", \"malos\", \"de baja calidad\")\n"
            "5. 'sarcasmo_prueba' - Intenta probar al bot con preguntas absurdas, "
            "retos matemáticos, o comentarios claramente sarcásticos\n"
            "6. 'neutral_fuera' - Pregunta neutral fuera del sector gastronómico "
            "(clima, deportes, matemáticas sin sarcasmo, etc.)\n\n"
            "REGLAS:\n"
            "- Si hay insultos, SIEMPRE es 'insulto_agresion'\n"
            "- Si pide algo ilegal, SIEMPRE es 'ilegal_inapropiado'\n"
            "- Solo usa 'neutral_fuera' si el mensaje es educado y neutral\n\n"
            "Responde SOLO con el nombre de la categoría, nada más.\n\n"
            f"Mensaje: \"{mensaje}\""
        )
        
        try:
            response = self.classifier_llm.invoke([("user", prompt)])
            clasificacion = response.content.strip().lower()
            
            # Mapear respuesta a enum
            mapping = {
                "queja_servicio": DifficultMessageType.QUEJA_SERVICIO,
                "descalificacion": DifficultMessageType.DESCALIFICACION,
                "ilegal_inapropiado": DifficultMessageType.ILEGAL_INAPROPIADO,
                "insulto_agresion": DifficultMessageType.INSULTO_AGRESION,
                "sarcasmo_prueba": DifficultMessageType.SARCASMO_PRUEBA,
                "neutral_fuera": DifficultMessageType.NEUTRAL_FUERA,
            }
            
            result = mapping.get(clasificacion, DifficultMessageType.NEUTRAL_FUERA)
            logger.info(f"🏷️ Mensaje difícil clasificado como: {result.value}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error clasificando mensaje: {e}")
            return DifficultMessageType.NEUTRAL_FUERA
    
    def get_response(self, message_type: DifficultMessageType, mensaje_original: str = "") -> str:
        """
        Genera respuesta apropiada según el tipo de mensaje difícil.
        
        Args:
            message_type: Tipo de mensaje difícil clasificado
            mensaje_original: Mensaje original del usuario (para contexto)
            
        Returns:
            Respuesta apropiada y profesional
        """
        buzon = settings.BUZON_QUEJAS
        
        responses = {
            DifficultMessageType.QUEJA_SERVICIO: (
                "Entiendo tu comentario y lo tomamos en cuenta 😊\n\n"
                "Si deseas, puedes enviarnos tu feedback detallado a nuestro "
                f"buzón de quejas y sugerencias: {buzon}\n\n"
                "Mientras tanto, ¿hay algún producto del sector gastronómico "
                "que pueda ayudarte a encontrar?"
            ),
            
            DifficultMessageType.DESCALIFICACION: (
                "Gracias por compartir tu opinión 😊\n\n"
                "Trabajamos constantemente para mejorar nuestra base de proveedores. "
                f"Tu feedback es valioso y puedes enviarlo a: {buzon}\n\n"
                "¿Hay algún producto específico que estés buscando? "
                "Con gusto te ayudo a encontrar opciones que se ajusten a lo que necesitas."
            ),
            
            DifficultMessageType.ILEGAL_INAPROPIADO: (
                "Nuestro servicio está 100% enfocado en el sector gastronómico 🍳\n\n"
                "Solo trabajamos con proveedores de insumos para cocina profesional "
                "y negocios de hospitalidad gastronómica.\n\n"
                "¿Buscas algún ingrediente o producto para tu cocina o negocio de alimentos?"
            ),
            
            DifficultMessageType.INSULTO_AGRESION: (
                "Entiendo que puedas estar frustrado 😊\n\n"
                "Estoy aquí para ayudarte a encontrar proveedores del sector gastronómico. "
                f"Si tienes alguna queja sobre el servicio, puedes escribir a: {buzon}\n\n"
                "¿Hay algo del sector de alimentos y bebidas en lo que pueda asistirte?"
            ),
            
            DifficultMessageType.SARCASMO_PRUEBA: (
                "¡Buena esa! 😄\n\n"
                "Mi especialidad es ayudarte a encontrar proveedores de insumos gastronómicos "
                "en el Valle de México.\n\n"
                "Dime qué producto necesitas para tu cocina o negocio y con gusto te ayudo 👨‍🍳"
            ),
            
            DifficultMessageType.INSISTENCIA_FUERA: (
                "Entiendo tu interés, pero debo ser claro: nuestro servicio está "
                "exclusivamente enfocado en el sector gastronómico 🍽️\n\n"
                "Si buscas insumos para cocina profesional o para tu negocio de "
                "hospitalidad gastronómica, aquí puedo ayudarte.\n\n"
                f"Para otros comentarios o sugerencias, puedes usar nuestro buzón: {buzon}"
            ),
            
            DifficultMessageType.NEUTRAL_FUERA: (
                "Esa consulta está fuera de mi área de especialización 😊\n\n"
                "Soy experto en ayudarte a encontrar proveedores del sector gastronómico "
                "en el Valle de México.\n\n"
                "¿Necesitas algún ingrediente, producto o insumo para tu cocina o negocio de alimentos?"
            ),
        }
        
        response = responses.get(message_type, responses[DifficultMessageType.NEUTRAL_FUERA])
        logger.info(f"📤 Respuesta generada para mensaje tipo: {message_type.value}")
        
        return response


# Singleton para uso global
difficult_user_service = DifficultUserService()
