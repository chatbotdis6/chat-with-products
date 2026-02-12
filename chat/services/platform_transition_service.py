"""
Servicio de transición a la plataforma - Strategy Pattern.

Este servicio detecta momentos naturales en la conversación donde el usuario
se beneficiaría de usar la plataforma web completa, y genera invitaciones
contextuales sin ser intrusivo.
"""
import logging
from typing import Optional, Dict, Any
from enum import Enum

from chat.config.settings import settings

logger = logging.getLogger(__name__)


class TransitionContext(Enum):
    """Contextos que disparan la sugerencia de transición a plataforma."""
    AFTER_PROVIDER_LIST = "after_provider_list"  # Después de mostrar lista de proveedores
    MULTIPLE_PROVIDERS_HIDDEN = "multiple_providers_hidden"  # Hay muchos proveedores ocultos
    AFTER_CONTACT_DETAILS = "after_contact_details"  # Después de mostrar contacto
    PRICE_COMPARISON_REQUEST = "price_comparison"  # Usuario pide comparar precios
    AFTER_SHOW_MORE = "after_show_more"  # Después de "mostrar más"
    MULTIPLE_BRANDS_AVAILABLE = "multiple_brands"  # Muchas marcas disponibles


class PlatformTransitionService:
    """
    Servicio que detecta momentos óptimos para sugerir la plataforma
    y genera mensajes contextuales e invitantes.
    
    Principios:
    - Nunca interrumpir, solo complementar
    - Mensajes contextuales, no genéricos
    - Destacar beneficios, no limitaciones
    - Natural y amigable
    """
    
    def __init__(self):
        """Inicializa el servicio de transición."""
        self.platform_url = settings.PLATFORM_URL
        logger.info(f"🌐 PlatformTransitionService inicializado - URL: {self.platform_url}")
    
    def should_suggest_transition(
        self,
        context: TransitionContext,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Determina si es un buen momento para sugerir la plataforma.
        
        Args:
            context: Contexto actual de la conversación
            metadata: Información adicional (ej: num proveedores ocultos, marcas disponibles)
            
        Returns:
            True si se debe sugerir la transición
        """
        metadata = metadata or {}
        
        # AFTER_PROVIDER_LIST: Siempre sugerir después de mostrar proveedores
        if context == TransitionContext.AFTER_PROVIDER_LIST:
            return True
        
        # MULTIPLE_PROVIDERS_HIDDEN: Solo si hay 3+ proveedores ocultos
        if context == TransitionContext.MULTIPLE_PROVIDERS_HIDDEN:
            hidden_count = metadata.get("proveedores_ocultos", 0)
            return hidden_count >= 3
        
        # AFTER_CONTACT_DETAILS: Siempre sugerir después de ver contacto
        if context == TransitionContext.AFTER_CONTACT_DETAILS:
            return True
        
        # PRICE_COMPARISON_REQUEST: Siempre sugerir cuando pide precios
        if context == TransitionContext.PRICE_COMPARISON_REQUEST:
            return True
        
        # AFTER_SHOW_MORE: Siempre sugerir después de "mostrar más"
        if context == TransitionContext.AFTER_SHOW_MORE:
            return True
        
        # MULTIPLE_BRANDS_AVAILABLE: Solo si hay 5+ marcas
        if context == TransitionContext.MULTIPLE_BRANDS_AVAILABLE:
            brands_count = metadata.get("marcas_disponibles", 0)
            return brands_count >= 5
        
        return False
    
    def generate_transition_message(
        self,
        context: TransitionContext,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Genera un mensaje contextual invitando a usar la plataforma.
        
        Args:
            context: Contexto actual de la conversación
            metadata: Información adicional para personalizar el mensaje
            
        Returns:
            Mensaje de transición apropiado para el contexto
        """
        metadata = metadata or {}
        
        # Mensajes específicos por contexto
        messages = {
            TransitionContext.AFTER_PROVIDER_LIST: self._message_after_provider_list(metadata),
            TransitionContext.MULTIPLE_PROVIDERS_HIDDEN: self._message_multiple_hidden(metadata),
            TransitionContext.AFTER_CONTACT_DETAILS: self._message_after_contact(metadata),
            TransitionContext.PRICE_COMPARISON_REQUEST: self._message_price_comparison(metadata),
            TransitionContext.AFTER_SHOW_MORE: self._message_after_show_more(metadata),
            TransitionContext.MULTIPLE_BRANDS_AVAILABLE: self._message_multiple_brands(metadata),
        }
        
        message = messages.get(context, self._message_default())
        
        logger.debug(f"💬 Mensaje de transición generado para contexto: {context.value}")
        return message
    
    def _message_after_provider_list(self, metadata: Dict[str, Any]) -> str:
        """Mensaje después de mostrar lista de proveedores."""
        hidden = metadata.get("proveedores_ocultos", 0)
        
        if hidden > 0:
            return (
                f"\n\n💡 **Tip**: Si quieres ver los {hidden} proveedores adicionales "
                f"y comparar presentaciones, precios y condiciones en un solo lugar, "
                f"prueba nuestro **Cuadro Comparativo** en la Plataforma: {self.platform_url}"
            )
        else:
            return (
                f"\n\n💡 **Tip**: En nuestra Plataforma puedes armar cuadros comparativos "
                f"personalizados, ver fichas completas de proveedores y filtrar por ubicación, "
                f"precio y más. Explórala aquí: {self.platform_url}"
            )
    
    def _message_multiple_hidden(self, metadata: Dict[str, Any]) -> str:
        """Mensaje cuando hay muchos proveedores ocultos."""
        hidden = metadata.get("proveedores_ocultos", 0)
        return (
            f"\n\n🔍 Hay {hidden} proveedores más que podrías explorar. "
            f"En la Plataforma puedes ver todos de un vistazo, filtrar por zona, "
            f"comparar precios y armar tu lista de favoritos: {self.platform_url}"
        )
    
    def _message_after_contact(self, metadata: Dict[str, Any]) -> str:
        """Mensaje después de mostrar detalles de contacto."""
        return (
            f"\n\n📊 **¿Sabías que...?** En la Plataforma puedes guardar proveedores favoritos, "
            f"ver su historial de entregas, comparar condiciones de pago y mucho más. "
            f"Accede aquí: {self.platform_url}"
        )
    
    def _message_price_comparison(self, metadata: Dict[str, Any]) -> str:
        """Mensaje cuando el usuario solicita comparación de precios."""
        return (
            f"\n\n💰 Para comparaciones de precio más detalladas, en la Plataforma puedes "
            f"crear **Cuadros Comparativos** con todas las presentaciones, rendimientos "
            f"y condiciones de entrega. Pruébalo aquí: {self.platform_url}"
        )
    
    def _message_after_show_more(self, metadata: Dict[str, Any]) -> str:
        """Mensaje después de usar 'mostrar más'."""
        return (
            f"\n\n🎯 Veo que buscas explorar a fondo tus opciones. En la Plataforma tienes "
            f"herramientas más potentes para comparar, filtrar y decidir con toda la información "
            f"a la vista. Conócela: {self.platform_url}"
        )
    
    def _message_multiple_brands(self, metadata: Dict[str, Any]) -> str:
        """Mensaje cuando hay muchas marcas disponibles."""
        brands_count = metadata.get("marcas_disponibles", 0)
        return (
            f"\n\n🏷️ Hay {brands_count} marcas diferentes disponibles. "
            f"En la Plataforma puedes filtrar por marca, comparar calidad-precio "
            f"y ver reseñas de otros compradores: {self.platform_url}"
        )
    
    def _message_default(self) -> str:
        """Mensaje por defecto si no hay contexto específico."""
        return (
            f"\n\n✨ **Por cierto**, en nuestra Plataforma puedes hacer mucho más: "
            f"cuadros comparativos, filtros avanzados, historial de precios y más. "
            f"Descúbrela aquí: {self.platform_url}"
        )
    
    def get_mandatory_redirect_message(self) -> str:
        """
        Mensaje de derivación obligatoria cuando el usuario ha excedido
        el número máximo de consultas en el chat (turno 6+).
        
        Este mensaje se muestra SIN usar LLM para ahorrar costos.
        """
        return (
            f"¡Gracias por usar nuestro chat! 😊\n\n"
            f"Para continuar explorando proveedores, comparar precios y acceder a "
            f"herramientas más completas como **Cuadros Comparativos** y **Filtros Avanzados**, "
            f"te invitamos a visitar nuestra **Plataforma**:\n\n"
            f"👉 {self.platform_url}\n\n"
            f"Allí podrás:\n"
            f"• Ver todos los proveedores disponibles\n"
            f"• Comparar precios y presentaciones\n"
            f"• Filtrar por ubicación y condiciones de pago\n"
            f"• Guardar tus proveedores favoritos\n\n"
            f"¡Te esperamos! 🚀"
        )
    
    def get_llm_derivation_prompt(self, user_message: str) -> str:
        """
        Genera un prompt especial para que el LLM derive al usuario a la plataforma
        de manera contextual, sin responder directamente a su pregunta.
        
        Se usa en el turno 5 (primera derivación obligatoria).
        
        Args:
            user_message: El mensaje original del usuario
        """
        return (
            f"[INSTRUCCIÓN DEL SISTEMA - NO MOSTRAR AL USUARIO]\n"
            f"El usuario ha realizado su quinta consulta. DEBES derivarlo a la plataforma "
            f"de manera amable y contextual, SIN responder a su pregunta directamente.\n\n"
            f"Mensaje del usuario: \"{user_message}\"\n\n"
            f"Tu respuesta debe:\n"
            f"1. Reconocer brevemente su interés (sin dar la información que pide)\n"
            f"2. Explicar que para continuar ayudándole mejor, lo ideal es usar la Plataforma\n"
            f"3. Destacar beneficios relevantes a su consulta (cuadros comparativos, filtros, etc.)\n"
            f"4. Incluir el enlace: {self.platform_url}\n"
            f"5. Ser amable y no hacerle sentir rechazado\n\n"
            f"NO uses herramientas de búsqueda. Solo genera el mensaje de derivación."
        )
    
    def get_soft_suggestion_message(self, consulta_numero: int) -> str:
        """
        Mensaje de sugerencia suave después de 2-3 consultas.
        Se añade al final de la respuesta normal del LLM.
        
        Args:
            consulta_numero: Número de consulta actual
        """
        if consulta_numero == 2:
            return (
                f"\n\n💡 **Tip**: Si quieres explorar más opciones y comparar proveedores, "
                f"en nuestra Plataforma puedes armar un Cuadro Comparativo con las mejores "
                f"opciones del mercado: {self.platform_url}"
            )
        elif consulta_numero == 3:
            return (
                f"\n\n🎯 **¿Sabías que...?** En la Plataforma tienes acceso a filtros avanzados, "
                f"historial de precios y evaluaciones de otros compradores. "
                f"Conócela: {self.platform_url}"
            )
        elif consulta_numero == 4:
            return (
                f"\n\n⭐ **Última sugerencia**: Para aprovechar al máximo tu búsqueda, "
                f"te recomendamos continuar en la Plataforma donde tendrás herramientas "
                f"más potentes para tomar la mejor decisión: {self.platform_url}"
            )
        return ""


logger.info("📦 Módulo platform_transition_service.py cargado")
