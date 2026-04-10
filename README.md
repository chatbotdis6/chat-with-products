# The Hap & D Company - Chat with Products 🛒

Chatbot conversacional para conectar usuarios con proveedores de insumos gastronómicos en el Valle de México.

## 🏗️ Arquitectura

El sistema utiliza **LangGraph** con un agente de tool-calling: el LLM decide qué herramienta usar en cada turno.

```
┌───────────────────────┐
│     Agent Node        │ ← LLM con 6 herramientas vinculadas
│   (system prompt +    │
│    historial)         │
└──────────┬────────────┘
           │
     ¿tool_calls?
     ├─ sí ──→ Tool Node (ejecuta herramienta) ──→ Agent Node (loop)
     └─ no ──→ END
```

### Herramientas disponibles
| Herramienta | Uso |
|------------|-----|
| `buscar_productos` | Buscar proveedores por producto/marca |
| `filtrar_por_precio` | Ordenar por precio, filtrar por rango |
| `detalle_proveedor` | Info de contacto, WhatsApp, web |
| `mostrar_mas_proveedores` | Ver más resultados |
| `consultar_especialista` | Chef, nutriólogo, bartender, barista, ing. alimentos |
| `reportar_producto_no_encontrado` | Clasificar y notificar al equipo |

## 🚀 Inicio Rápido

```bash
# 1. Activar entorno virtual
source .venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 4. Iniciar demo (Streamlit)
streamlit run chat_streamlit.py --server.port 8502
```

## 📁 Estructura del Proyecto

```
chat/
├── agent/                  # Agente tool-calling
│   ├── chatbot.py         # Entry point: Chatbot class
│   ├── graph.py           # StateGraph (2 nodos: agent + tools)
│   ├── tools.py           # 6 herramientas @tool
│   └── prompts.py         # System prompt dinámico
├── graph/                  # Lógica reutilizada por las tools
│   ├── state.py           # Tipos (ConversationState, etc.)
│   └── nodes/
│       └── query.py       # Text-to-SQL + búsqueda híbrida
├── config/
│   └── settings.py        # Configuración centralizada
├── models/
│   └── types.py           # ProductoInfo, ProveedorInfo
├── services/
│   ├── data_transformer.py # Transformación DB → tipos
│   ├── email_service.py   # Notificaciones SendGrid/SMTP
│   └── whatsapp_formatter.py # Formateo números WhatsApp
└── prompts/
    └── system_prompts.py  # Prompt conversacional
```

## 🎭 Funcionalidades

### Búsqueda de Productos
| Acción | Ejemplo | Resultado |
|--------|---------|-----------|
| Búsqueda inicial | "Busco mantequilla" | Lista de proveedores con marcas disponibles |
| Filtrar por marca | "Carbonell" | Proveedores con esa marca |
| Ver precios | "Dame los más baratos" | Lista ordenada por precio |
| Info proveedor | "Más info de La Ranita" | Contacto, WhatsApp, web, calificación |

### Agentes Especializados
| Agente | Descripción | Ejemplo |
|--------|-------------|---------|
| 🔍 **Búsqueda** | Proveedores y productos | "Busco mantequilla" |
| 👨‍🍳 **Chef** | Recetas y técnicas | "¿Cómo hacer fresas Dubai?" |
| 🥗 **Nutriólogo** | Info nutricional | "¿Calorías del aguacate?" |
| 🍹 **Bartender** | Cócteles | "¿Cómo preparar Margarita?" |
| ☕ **Barista** | Café | "¿Técnica de latte art?" |
| 🔬 **Ing. Alimentos** | Conservación | "¿Cómo conservar mariscos?" |

## 🔧 Configuración

Variables de entorno requeridas en `.env`:

```bash
# OpenAI
OPENAI_API_KEY="sk-..."

# Modelos LLM (cada uno optimizado para su tarea)
CHAT_MODEL="gpt-4.1"         # Conversación natural y creativa
ROUTER_MODEL="gpt-4o"        # Clasificación + extracción de entidades
SQL_MODEL="o3-mini"          # Text-to-SQL (razonamiento sobre estructura)

# Base de datos PostgreSQL
DATABASE_URL="postgresql://user:pass@host:port/db"

# Email (SendGrid)
SENDGRID_API_KEY="SG...."
EMAIL_FROM="chatbot@empresa.com"
BUZON_QUEJAS="quejas@empresa.com"
```

### Uso de modelos:

| Modelo | Tarea | Justificación |
|--------|-------|---------------|
| **gpt-4.1** | Chat, Specialists | Conversación natural, creatividad |
| **gpt-4o** | Router | JSON estructurado, clasificación rápida |
| **o3-mini** | Text-to-SQL | Razonamiento sobre estructura de BD, búsqueda híbrida (trigram + vector) |

## 📱 Preparado para WhatsApp

El sistema usa estado en memoria por sesión (dict `_sessions` en `whatsapp_server.py`).

```python
from chat.agent.chatbot import Chatbot

# Crear bot para un usuario de WhatsApp
bot = Chatbot(
    session_id="+5255XXXXXXXX",  # Número de WhatsApp
)

# Las conversaciones persisten mientras el dyno esté activo
response = bot.chat("Hola")
```

## 🧪 Testing

```bash
# Tests unitarios
pytest test_chatbot.py -v

# Test rápido
python -c "from chat.agent.chatbot import Chatbot; print(Chatbot().chat('Hola'))"

# Test conversación con precios
python -c "
from chat.agent.chatbot import Chatbot
bot = Chatbot(session_id='test')
print(bot.chat('Busco aceite de oliva'))
print(bot.chat('Dame los más baratos'))
print(bot.chat('Más info de La Ranita De La Paz'))
"
```

## 📚 Documentación

- [Arquitectura](chat/ARCHITECTURE.md) - Detalles técnicos
- [Platform Transition Strategy](docs/PLATFORM_TRANSITION_STRATEGY.md) - Lógica de derivación
- [ETL Operations](docs/DOCUMENTATION_ETL.md) - Ingesta de datos

## 🛠️ Tech Stack

- **Orquestación:** LangGraph 1.0.7
- **LLM:** OpenAI GPT-4o / GPT-5 / o3-mini
- **Base de datos:** PostgreSQL + pgvector + pg_trgm
- **Búsqueda:** Híbrida (trigram similarity + vector embeddings)
- **Sesión:** Estado en memoria (por dyno)
- **Email:** SendGrid / SMTP
- **WhatsApp:** Twilio (webhook + REST API)
- **Deploy:** Heroku
- **UI Demo:** Streamlit
