# The Hap & D Company - Chat with Products 🛒

Chatbot conversacional para conectar usuarios con proveedores de insumos gastronómicos en el Valle de México.

## 🏗️ Arquitectura

El sistema utiliza **LangGraph 1.0.7** para orquestar el flujo de conversación como un grafo de estados:

```
┌─────────────┐
│   Router    │ ← 1 LLM call: intent + entities + difficult user
└──────┬──────┘
       │
       ├── busqueda_proveedores → Query Node (Text-to-SQL)
       ├── filtrar_precio ────────────┘
       ├── detalle_proveedor ─────────┘
       ├── chef/nutriologo/... → Specialist Node
       └── fuera_alcance → Difficult User Node
                          │
                          ▼
                   ┌─────────────┐
                   │  Response   │
                   └──────┬──────┘
                          │
                          ▼
                   ┌─────────────┐
                   │ Transition  │ → Sugiere plataforma
                   └──────┬──────┘
                          │
                          ▼
                        END
```

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
streamlit run chat_streamlit_v2.py --server.port 8502
```

## 📁 Estructura del Proyecto

```
chat/
├── chatbot_v2.py           # Entry point principal
├── graph/                  # 🆕 Arquitectura LangGraph
│   ├── state.py           # ConversationState TypedDict
│   ├── graph.py           # StateGraph assembly
│   ├── checkpointer.py    # PostgreSQL persistence
│   └── nodes/             # Nodos del grafo
│       ├── router.py      # Intent + entities + difficult
│       ├── query.py       # Text-to-SQL + búsqueda híbrida
│       ├── specialist.py  # Chef, Nutriólogo, etc.
│       ├── difficult_user.py
│       ├── unregistered.py
│       ├── response.py
│       └── transition.py
├── config/
│   └── settings.py        # Configuración centralizada
├── services/
│   ├── search_service.py  # Búsqueda híbrida
│   ├── email_service.py   # Notificaciones SendGrid
│   └── ...
└── prompts/
    └── system_prompts.py  # Prompts de sistema
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

El sistema usa `langgraph-checkpoint-postgres` para persistencia de sesiones:

```python
from chat.chatbot_v2 import ChatbotV2

# Crear bot con persistencia (para WhatsApp)
bot = ChatbotV2(
    session_id="+5255XXXXXXXX",  # Número de WhatsApp
    use_persistence=True
)

# Las conversaciones persisten entre sesiones
response = bot.chat("Hola")
```

## 🧪 Testing

```bash
# Test rápido
python -c "from chat.chatbot_v2 import ChatbotV2; print(ChatbotV2().chat('Hola'))"

# Test flujo completo
python test_architecture.py

# Test conversación con precios
python -c "
from chat.chatbot_v2 import ChatbotV2
bot = ChatbotV2(session_id='test')
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
- **LLM:** OpenAI GPT-4o / o3-mini
- **Base de datos:** PostgreSQL + pgvector + pg_trgm
- **Búsqueda:** Híbrida (trigram similarity + vector embeddings)
- **Persistencia:** langgraph-checkpoint-postgres
- **Email:** SendGrid
- **UI Demo:** Streamlit
