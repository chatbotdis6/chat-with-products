"""
Test del servicio de transición a plataforma.

Verifica que los disparadores y mensajes contextuales funcionen correctamente.
"""
import sys
import os

# Añadir directorio raíz al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from chat.services.platform_transition_service import (
    PlatformTransitionService,
    TransitionContext
)


def test_platform_transition_service():
    """Test básico del servicio de transición."""
    service = PlatformTransitionService()
    
    print("=" * 60)
    print("🧪 TEST: PlatformTransitionService")
    print("=" * 60)
    
    # Test 1: AFTER_PROVIDER_LIST con proveedores ocultos
    print("\n📋 Test 1: Después de mostrar proveedores (con ocultos)")
    metadata1 = {"proveedores_ocultos": 5, "marcas_disponibles": 3}
    
    should_suggest = service.should_suggest_transition(
        TransitionContext.AFTER_PROVIDER_LIST,
        metadata1
    )
    print(f"   ¿Debe sugerir? {should_suggest}")
    
    if should_suggest:
        message = service.generate_transition_message(
            TransitionContext.AFTER_PROVIDER_LIST,
            metadata1
        )
        print(f"   Mensaje:\n   {message}\n")
    
    # Test 2: MULTIPLE_BRANDS_AVAILABLE
    print("\n📋 Test 2: Múltiples marcas disponibles")
    metadata2 = {"marcas_disponibles": 8}
    
    should_suggest = service.should_suggest_transition(
        TransitionContext.MULTIPLE_BRANDS_AVAILABLE,
        metadata2
    )
    print(f"   ¿Debe sugerir? {should_suggest}")
    
    if should_suggest:
        message = service.generate_transition_message(
            TransitionContext.MULTIPLE_BRANDS_AVAILABLE,
            metadata2
        )
        print(f"   Mensaje:\n   {message}\n")
    
    # Test 3: AFTER_SHOW_MORE
    print("\n📋 Test 3: Después de 'mostrar más'")
    should_suggest = service.should_suggest_transition(
        TransitionContext.AFTER_SHOW_MORE
    )
    print(f"   ¿Debe sugerir? {should_suggest}")
    
    if should_suggest:
        message = service.generate_transition_message(
            TransitionContext.AFTER_SHOW_MORE,
            {"proveedores_mostrados": 7}
        )
        print(f"   Mensaje:\n   {message}\n")
    
    # Test 4: AFTER_CONTACT_DETAILS
    print("\n📋 Test 4: Después de ver detalles de contacto")
    should_suggest = service.should_suggest_transition(
        TransitionContext.AFTER_CONTACT_DETAILS
    )
    print(f"   ¿Debe sugerir? {should_suggest}")
    
    if should_suggest:
        message = service.generate_transition_message(
            TransitionContext.AFTER_CONTACT_DETAILS,
            {"proveedor": "Alimentos BAAB"}
        )
        print(f"   Mensaje:\n   {message}\n")
    
    # Test 5: PRICE_COMPARISON_REQUEST
    print("\n📋 Test 5: Solicitud de comparación de precios")
    should_suggest = service.should_suggest_transition(
        TransitionContext.PRICE_COMPARISON_REQUEST
    )
    print(f"   ¿Debe sugerir? {should_suggest}")
    
    if should_suggest:
        message = service.generate_transition_message(
            TransitionContext.PRICE_COMPARISON_REQUEST
        )
        print(f"   Mensaje:\n   {message}\n")
    
    # Test 6: MULTIPLE_PROVIDERS_HIDDEN (no debería sugerir con pocos ocultos)
    print("\n📋 Test 6: Pocos proveedores ocultos (no debe sugerir)")
    metadata6 = {"proveedores_ocultos": 1}
    should_suggest = service.should_suggest_transition(
        TransitionContext.MULTIPLE_PROVIDERS_HIDDEN,
        metadata6
    )
    print(f"   ¿Debe sugerir? {should_suggest} (esperado: False)")
    
    # Test 7: MULTIPLE_PROVIDERS_HIDDEN (sí debe sugerir con muchos)
    print("\n📋 Test 7: Muchos proveedores ocultos (debe sugerir)")
    metadata7 = {"proveedores_ocultos": 10}
    should_suggest = service.should_suggest_transition(
        TransitionContext.MULTIPLE_PROVIDERS_HIDDEN,
        metadata7
    )
    print(f"   ¿Debe sugerir? {should_suggest} (esperado: True)")
    
    if should_suggest:
        message = service.generate_transition_message(
            TransitionContext.MULTIPLE_PROVIDERS_HIDDEN,
            metadata7
        )
        print(f"   Mensaje:\n   {message}\n")
    
    print("=" * 60)
    print("✅ Tests completados")
    print("=" * 60)


if __name__ == "__main__":
    test_platform_transition_service()
