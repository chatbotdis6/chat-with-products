"""
Script de testing simple para verificar la nueva arquitectura.
"""
import sys
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def test_config():
    """Test de configuración."""
    try:
        from chat.config import settings
        logger.info("✅ Config importado correctamente")
        logger.info(f"   - CHAT_MODEL: {settings.CHAT_MODEL}")
        logger.info(f"   - BUZON_QUEJAS: {settings.BUZON_QUEJAS}")
        return True
    except Exception as e:
        logger.error(f"❌ Error en config: {e}")
        return False


def test_models():
    """Test de modelos de tipos."""
    try:
        from chat.models import IntentType, RelevanciaLevel
        logger.info("✅ Models importados correctamente")
        logger.info(f"   - IntentType: {list(IntentType)[:3]}")
        logger.info(f"   - RelevanciaLevel: {list(RelevanciaLevel)}")
        return True
    except Exception as e:
        logger.error(f"❌ Error en models: {e}")
        return False


def test_prompts():
    """Test de prompts."""
    try:
        from chat.prompts import system_prompts
        logger.info("✅ Prompts importados correctamente")
        main_prompt = system_prompts.get_main_prompt()
        logger.info(f"   - Main prompt length: {len(main_prompt)} chars")
        return True
    except Exception as e:
        logger.error(f"❌ Error en prompts: {e}")
        return False


def test_services():
    """Test de servicios."""
    try:
        from chat.services import (
            WhatsAppFormatter,
            DataTransformer,
        )
        logger.info("✅ Services importados correctamente")
        
        # Test WhatsAppFormatter
        nums, links = WhatsAppFormatter.format_numbers("5555551234, 5555555678")
        logger.info(f"   - WhatsAppFormatter: {len(nums)} números formateados")
        
        return True
    except Exception as e:
        logger.error(f"❌ Error en services: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_agents():
    """Test de agentes."""
    try:
        from chat.agents import (
            ChefAgent,
            NutriologoAgent,
            BartenderAgent,
            BaristaAgent,
            IngenieroAgent,
        )
        logger.info("✅ Agents importados correctamente")
        logger.info(f"   - ChefAgent disponible")
        logger.info(f"   - NutriologoAgent disponible")
        logger.info(f"   - BartenderAgent disponible")
        logger.info(f"   - BaristaAgent disponible")
        logger.info(f"   - IngenieroAgent disponible")
        return True
    except Exception as e:
        logger.error(f"❌ Error en agents: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tools():
    """Test de tools."""
    try:
        from chat.tools import TOOLS
        logger.info("✅ Tools importadas correctamente")
        logger.info(f"   - Total tools: {len(TOOLS)}")
        for tool in TOOLS:
            logger.info(f"     • {tool.name}")
        return True
    except Exception as e:
        logger.error(f"❌ Error en tools: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_chatbot():
    """Test del chatbot principal."""
    try:
        from chat.chatbot_refactored import Chatbot
        logger.info("✅ Chatbot importado correctamente")
        
        # No instanciar para evitar dependencias de BD en test rápido
        logger.info("   - Clase Chatbot disponible")
        return True
    except Exception as e:
        logger.error(f"❌ Error en chatbot: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_compatibility():
    """Test de capa de compatibilidad."""
    try:
        from chat import search_compat
        logger.info("✅ Capa de compatibilidad disponible")
        logger.info(f"   - Funciones exportadas: {search_compat.__all__}")
        return True
    except Exception as e:
        logger.error(f"❌ Error en compatibility: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Ejecuta todos los tests."""
    logger.info("=" * 60)
    logger.info("🧪 TESTING NUEVA ARQUITECTURA")
    logger.info("=" * 60)
    
    tests = [
        ("Configuración", test_config),
        ("Modelos de tipos", test_models),
        ("Prompts", test_prompts),
        ("Servicios", test_services),
        ("Agentes", test_agents),
        ("Tools", test_tools),
        ("Chatbot", test_chatbot),
        ("Compatibilidad", test_compatibility),
    ]
    
    results = []
    for name, test_func in tests:
        logger.info("")
        logger.info(f"🔍 Testing: {name}")
        logger.info("-" * 60)
        result = test_func()
        results.append((name, result))
        logger.info("-" * 60)
    
    # Resumen
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 RESUMEN DE TESTS")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status} - {name}")
    
    logger.info("=" * 60)
    logger.info(f"Total: {passed}/{total} tests pasados")
    logger.info("=" * 60)
    
    if passed == total:
        logger.info("🎉 ¡Todos los tests pasaron exitosamente!")
        return 0
    else:
        logger.warning(f"⚠️  {total - passed} test(s) fallaron")
        return 1


if __name__ == "__main__":
    sys.exit(main())
