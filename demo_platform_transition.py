#!/usr/bin/env python3
"""
Script de demostración de la estrategia de transición a plataforma.

Muestra cómo los diferentes contextos generan mensajes específicos
y cómo se integran en las respuestas del chatbot.
"""
import sys
import os

# Añadir directorio raíz al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from chat.services.platform_transition_service import (
    PlatformTransitionService,
    TransitionContext
)


def print_separator(char="=", length=70):
    """Imprime una línea separadora."""
    print(char * length)


def print_section(title):
    """Imprime un título de sección."""
    print_separator()
    print(f"📋 {title}")
    print_separator()


def demo_scenario_1():
    """Escenario 1: Búsqueda simple de mantequilla."""
    print_section("ESCENARIO 1: Búsqueda simple con marca específica")
    
    print("\n👤 Usuario: 'Busco mantequilla'")
    print("🤖 Bot: 'Tenemos varias marcas: Anchor, Lyncott, Président. ¿Preferencia?'\n")
    
    print("👤 Usuario: 'Sí, Anchor'")
    print("🤖 Bot (respuesta simulada):\n")
    
    # Simular respuesta del bot
    print("¡Perfecto! Estos son los principales proveedores que manejan mantequilla Anchor:\n")
    print("1. **Alimentos BAAB**")
    print("   - Empresa mayorista que importa productos lácteos premium. Ejemplos: mantequilla\n")
    print("2. **Standard Food Company**")
    print("   - Distribuidora mayorista de lácteos y embutidos. Ejemplos: mantequilla\n")
    print("¿Quieres más información de algún proveedor en particular? 😉\n")
    
    # Generar sugerencia de plataforma
    service = PlatformTransitionService()
    metadata = {"proveedores_ocultos": 4, "marcas_disponibles": 1}
    
    if service.should_suggest_transition(TransitionContext.AFTER_PROVIDER_LIST, metadata):
        suggestion = service.generate_transition_message(
            TransitionContext.AFTER_PROVIDER_LIST,
            metadata
        )
        print(suggestion)
    
    print("\n" + "─" * 70)
    print("💡 Observación: Mensaje aparece DESPUÉS de respuesta completa")
    print("─" * 70 + "\n")


def demo_scenario_2():
    """Escenario 2: Usuario explorando proveedores a fondo."""
    print_section("ESCENARIO 2: Usuario usa 'mostrar más'")
    
    print("\n👤 Usuario: 'Muéstrame más proveedores de aceite'")
    print("🤖 Bot (respuesta simulada):\n")
    
    print("**Proveedores adicionales para 'aceite'**:\n")
    print("4. **Proveedor C** — ej.: aceite de oliva, aceite de girasol")
    print("5. **Proveedor D** — ej.: aceite vegetal, aceite de coco")
    print("6. **Proveedor E** — ej.: aceite de aguacate, aceite de sésamo\n")
    print("¿Quieres más información de alguno? 😉\n")
    
    # Generar sugerencia de plataforma
    service = PlatformTransitionService()
    suggestion = service.generate_transition_message(
        TransitionContext.AFTER_SHOW_MORE,
        {"proveedores_mostrados": 3}
    )
    print(suggestion)
    
    print("\n" + "─" * 70)
    print("💡 Observación: Usuario explorando a fondo = momento perfecto para ofrecer herramientas avanzadas")
    print("─" * 70 + "\n")


def demo_scenario_3():
    """Escenario 3: Usuario solicita detalles de contacto."""
    print_section("ESCENARIO 3: Usuario pide detalles de proveedor")
    
    print("\n👤 Usuario: 'Quiero el contacto de Alimentos BAAB'")
    print("🤖 Bot (respuesta simulada):\n")
    
    print("**Detalles de Alimentos BAAB:**")
    print("- **Vendedor:** Juan Pérez")
    print("- **WhatsApp:** [+52 55 1234 5678](https://wa.me/5255123456789)")
    print("- **Sitio web:** www.alimentosbaab.com\n")
    
    # Generar sugerencia de plataforma
    service = PlatformTransitionService()
    suggestion = service.generate_transition_message(
        TransitionContext.AFTER_CONTACT_DETAILS,
        {"proveedor": "Alimentos BAAB"}
    )
    print(suggestion)
    
    print("\n" + "─" * 70)
    print("💡 Observación: Usuario en fase de decisión = momento para mencionar funcionalidades avanzadas")
    print("─" * 70 + "\n")


def demo_scenario_4():
    """Escenario 4: Usuario busca el más barato."""
    print_section("ESCENARIO 4: Comparación de precios")
    
    print("\n👤 Usuario: '¿Cuál es el más barato?'")
    print("🤖 Bot (respuesta simulada):\n")
    
    print("Basándome en precios actuales:\n")
    print("1. **Proveedor A** - $45 MXN por kg")
    print("2. **Proveedor B** - $52 MXN por kg")
    print("3. **Proveedor C** - $58 MXN por kg\n")
    
    # Generar sugerencia de plataforma
    service = PlatformTransitionService()
    suggestion = service.generate_transition_message(
        TransitionContext.PRICE_COMPARISON_REQUEST
    )
    print(suggestion)
    
    print("\n" + "─" * 70)
    print("💡 Observación: Comparación de precios = funcionalidad clave de la plataforma")
    print("─" * 70 + "\n")


def demo_scenario_5():
    """Escenario 5: Producto con muchas marcas."""
    print_section("ESCENARIO 5: Producto con muchas marcas disponibles")
    
    print("\n👤 Usuario: 'Busco queso'")
    print("🤖 Bot (respuesta simulada):\n")
    
    print("Encontré proveedores de queso. Marcas disponibles:")
    print("Manchego, Gouda, Cheddar, Parmesano, Brie, Camembert, Roquefort, Gruyère...\n")
    print("¿Tienes preferencia por alguna marca? 😊\n")
    
    # Generar sugerencia de plataforma
    service = PlatformTransitionService()
    metadata = {"marcas_disponibles": 12}
    
    if service.should_suggest_transition(TransitionContext.MULTIPLE_BRANDS_AVAILABLE, metadata):
        suggestion = service.generate_transition_message(
            TransitionContext.MULTIPLE_BRANDS_AVAILABLE,
            metadata
        )
        print(suggestion)
    
    print("\n" + "─" * 70)
    print("💡 Observación: 12 marcas = imposible comparar bien en chat, plataforma es mejor opción")
    print("─" * 70 + "\n")


def demo_umbrales():
    """Demostración de umbrales inteligentes."""
    print_section("DEMOSTRACIÓN DE UMBRALES INTELIGENTES")
    
    service = PlatformTransitionService()
    
    print("\n🔍 Umbrales para MULTIPLE_BRANDS_AVAILABLE:")
    print("   Requiere: 5+ marcas\n")
    
    test_cases = [2, 4, 5, 8, 12]
    for count in test_cases:
        metadata = {"marcas_disponibles": count}
        should = service.should_suggest_transition(
            TransitionContext.MULTIPLE_BRANDS_AVAILABLE,
            metadata
        )
        status = "✅ SÍ" if should else "❌ NO"
        print(f"   Con {count:2d} marcas → {status} sugiere")
    
    print("\n🔍 Umbrales para MULTIPLE_PROVIDERS_HIDDEN:")
    print("   Requiere: 3+ proveedores ocultos\n")
    
    test_cases = [1, 2, 3, 5, 10]
    for count in test_cases:
        metadata = {"proveedores_ocultos": count}
        should = service.should_suggest_transition(
            TransitionContext.MULTIPLE_PROVIDERS_HIDDEN,
            metadata
        )
        status = "✅ SÍ" if should else "❌ NO"
        print(f"   Con {count:2d} ocultos → {status} sugiere")
    
    print("\n" + "─" * 70)
    print("💡 Observación: Umbrales evitan sugerir plataforma innecesariamente")
    print("─" * 70 + "\n")


def main():
    """Función principal de demostración."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 10 + "DEMOSTRACIÓN: ESTRATEGIA DE TRANSICIÓN A PLATAFORMA" + " " * 6 + "║")
    print("╚" + "═" * 68 + "╝")
    print("\n")
    
    # Ejecutar escenarios
    demo_scenario_1()
    input("Presiona Enter para continuar...\n")
    
    demo_scenario_2()
    input("Presiona Enter para continuar...\n")
    
    demo_scenario_3()
    input("Presiona Enter para continuar...\n")
    
    demo_scenario_4()
    input("Presiona Enter para continuar...\n")
    
    demo_scenario_5()
    input("Presiona Enter para continuar...\n")
    
    demo_umbrales()
    
    print_separator("=")
    print("✅ DEMOSTRACIÓN COMPLETA")
    print_separator("=")
    print("\n📚 Para más información, consulta: PLATFORM_TRANSITION_STRATEGY.md\n")


if __name__ == "__main__":
    main()
