"""Servicio de filtrado con LLM - Open/Closed Principle."""
import os
import logging
from typing import List
from langchain_openai import ChatOpenAI

from chat.models.types import ProductoInfo
from chat.config.settings import settings

logger = logging.getLogger(__name__)


class ProductFilterService:
    """Servicio para filtrar productos usando LLM."""
    
    def __init__(self):
        """Inicializa el servicio de filtrado."""
        self.llm = ChatOpenAI(model=settings.CHAT_MODEL)
        logger.info("✅ ProductFilterService inicializado")
    
    def filter_with_llm(
        self,
        productos: List[ProductoInfo],
        consulta_original: str
    ) -> List[ProductoInfo]:
        """
        Filtra productos usando LLM para evaluar relevancia real.
        
        Args:
            productos: Lista de productos a evaluar
            consulta_original: Consulta original del usuario
            
        Returns:
            Lista filtrada de productos relevantes
        """
        if not productos:
            return []
        
        logger.info(f"🤖 ══════════════════════════════════════════════════════")
        logger.info(f"🤖 FILTRADO INTELIGENTE CON LLM")
        logger.info(f"🔍 Consulta: '{consulta_original}' | Productos a evaluar: {len(productos)}")
        
        # Si hay muy pocos productos, no vale la pena filtrar
        if len(productos) <= 3:
            logger.info(f"⚡ Solo {len(productos)} productos, se omite filtrado LLM")
            logger.info(f"🤖 ══════════════════════════════════════════════════════")
            return productos
        
        # Construir lista de productos para evaluar (máximo 20)
        productos_para_evaluar = []
        limite = min(len(productos), 20)
        
        for idx in range(limite):
            p = productos[idx]
            # Obtener categorías si están disponibles
            categorias_str = ""
            if p.get("categorias") and isinstance(p["categorias"], list):
                cats = [c for c in p["categorias"] if c]
                if cats:
                    categorias_str = f" | Categorías: {', '.join(cats)}"
            
            productos_para_evaluar.append(
                f"{idx}. {p['producto']}" + 
                (f" ({p['marca']})" if p.get('marca') else "") + 
                categorias_str
            )
        
        productos_texto = "\n".join(productos_para_evaluar)
        logger.debug(f"📝 Enviando {len(productos_para_evaluar)} productos al LLM para evaluación")
        
        prompt_filtro = f"""Eres un experto en productos gastronómicos del sector de alimentos y bebidas.

Un cliente busca: "{consulta_original}"

Evalúa estos productos y determina cuáles SON REALMENTE RELEVANTES para esa búsqueda específica.

PRODUCTOS A EVALUAR:
{productos_texto}

CRITERIOS DE RELEVANCIA:
1. El producto debe ser DIRECTAMENTE útil para alguien que busca "{consulta_original}"
2. Verifica que TANTO el nombre del producto COMO sus categorías coincidan con la intención de búsqueda
3. DESCARTA productos que:
   - Solo contienen la palabra en su nombre pero pertenecen a otra categoría
   - Son ingredientes secundarios o derivados que contienen el término
   - No son lo que realmente buscaría un comprador profesional de ese producto

EJEMPLOS GENERALES DE RAZONAMIENTO:
- Si alguien busca un INGREDIENTE (como mantequilla, aceite, harina):
  ✅ Mantener: Productos que SON ese ingrediente
  ❌ Eliminar: Productos que CONTIENEN ese ingrediente pero son otra cosa (pan de mantequilla, galletas con aceite)

- Si alguien busca una BEBIDA:
  ✅ Mantener: Productos de categorías como bebidas, licores, refrescos
  ❌ Eliminar: Alimentos sólidos que contienen esa bebida como ingrediente

- Si alguien busca un TIPO DE ALIMENTO (pan, pasta, queso):
  ✅ Mantener: Productos de esa categoría principal
  ❌ Eliminar: Productos de otras categorías que incluyen ese alimento como parte

IMPORTANTE:
- Si las categorías indican claramente que es otro tipo de producto, DESCÁRTALO
- Usa tu conocimiento gastronómico para determinar qué buscaría realmente un profesional

FORMATO DE RESPUESTA:
Responde SOLO con los números de los productos RELEVANTES, separados por comas.
Si NINGUNO es relevante, responde: NINGUNO
NO incluyas explicaciones ni texto adicional, SOLO números.

Ejemplo de respuesta válida: 0, 2, 5, 8
"""
        
        try:
            response = self.llm.invoke([("user", prompt_filtro)])
            respuesta = response.content.strip()
            
            logger.info(f"🤖 LLM respondió: '{respuesta}'")
            
            # Parsear respuesta
            if respuesta.upper() == "NINGUNO":
                logger.warning(f"⚠️  LLM marcó TODOS los productos como irrelevantes")
                logger.info(f"🤖 ══════════════════════════════════════════════════════")
                return []
            
            # Extraer índices numéricos
            indices_str = respuesta.replace(" ", "").split(",")
            indices_validos = []
            
            for idx_str in indices_str:
                try:
                    idx = int(idx_str)
                    if 0 <= idx < len(productos):
                        indices_validos.append(idx)
                except ValueError:
                    logger.warning(f"⚠️  Índice inválido del LLM: '{idx_str}'")
            
            productos_filtrados = [productos[i] for i in indices_validos]
            
            logger.info(f"✅ Filtrado completado: {len(productos_filtrados)}/{len(productos)} productos relevantes")
            logger.info(f"🤖 ══════════════════════════════════════════════════════")
            
            return productos_filtrados
            
        except Exception as e:
            logger.error(f"❌ Error en filtrado LLM: {e}", exc_info=True)
            logger.warning(f"⚠️  Retornando productos sin filtrar debido al error")
            logger.info(f"🤖 ══════════════════════════════════════════════════════")
            return productos
