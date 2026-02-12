"""Servicio principal de búsqueda - Facade Pattern."""
import logging
from typing import Tuple, List, Optional

from chat.models.types import ProductoInfo, ProveedorInfo, RelevanciaLevel
from chat.config.settings import settings
from chat.services.database_service import DatabaseService
from chat.services.data_transformer import DataTransformer
from chat.services.product_filter_service import ProductFilterService

logger = logging.getLogger(__name__)


class SearchService:
    """
    Servicio principal de búsqueda - Facade que coordina todos los servicios.
    Aplica Facade Pattern para simplificar la interfaz de búsqueda.
    """
    
    def __init__(self):
        """Inicializa el servicio de búsqueda."""
        self.db = DatabaseService()
        self.transformer = DataTransformer()
        self.filter = ProductFilterService()
        logger.info("✅ SearchService inicializado")
    
    def buscar_productos_mejorado(
        self,
        search_query: str,
        top_k: int = None,
        knn_limit: int = None,
        threshold_trgm: float = None,
        threshold_vector: float = None,
        w_trgm: float = None,
        w_vec: float = None,
    ) -> Tuple[List[ProductoInfo], List[ProveedorInfo]]:
        """
        Búsqueda híbrida de productos (trigram + vector).
        
        Args:
            search_query: Consulta de búsqueda
            top_k: Número máximo de productos (default: settings.DEFAULT_TOP_K)
            knn_limit: Límite de candidatos vectoriales (default: settings.DEFAULT_KNN_LIMIT)
            threshold_trgm: Umbral trigram (default: settings.DEFAULT_THRESHOLD_TRGM)
            threshold_vector: Umbral vectorial (default: settings.DEFAULT_THRESHOLD_VECTOR)
            w_trgm: Peso trigram (default: settings.WEIGHT_TRGM)
            w_vec: Peso vectorial (default: settings.WEIGHT_VEC)
            
        Returns:
            Tuple de (productos, proveedores)
        """
        # Usar defaults de settings si no se especifican
        top_k = top_k or settings.DEFAULT_TOP_K
        knn_limit = knn_limit or settings.DEFAULT_KNN_LIMIT
        threshold_trgm = threshold_trgm if threshold_trgm is not None else settings.DEFAULT_THRESHOLD_TRGM
        threshold_vector = threshold_vector if threshold_vector is not None else settings.DEFAULT_THRESHOLD_VECTOR
        w_trgm = w_trgm if w_trgm is not None else settings.WEIGHT_TRGM
        w_vec = w_vec if w_vec is not None else settings.WEIGHT_VEC
        
        logger.info(
            f"🔍 Búsqueda iniciada: query='{search_query}', top_k={top_k}, "
            f"threshold_trgm={threshold_trgm}, threshold_vector={threshold_vector}"
        )
        
        # Búsqueda en base de datos
        prod_rows = self.db.search_products(
            search_query=search_query,
            top_k=top_k,
            knn_limit=knn_limit,
            threshold_trgm=threshold_trgm,
            threshold_vector=threshold_vector,
            w_trgm=w_trgm,
            w_vec=w_vec,
        )
        
        # Transformar filas a ProductoInfo
        productos = [self.transformer.row_to_producto(row) for row in prod_rows]
        
        # Log de productos con similitudes
        if productos:
            logger.info(f"📋 Productos encontrados con similitudes:")
            for i, p in enumerate(productos[:10], 1):
                logger.info(
                    f"  {i}. '{p['producto']}' ({p['proveedor']}) - "
                    f"Score: {p['score']:.3f} | "
                    f"Trgm: {p['similaridad_trgm']:.3f} | "
                    f"Vec: {p['similaridad_vector']:.3f}"
                )
            if len(productos) > 10:
                logger.info(f"  ... y {len(productos) - 10} productos más")
        
        # Agrupar por proveedores
        proveedores = self.transformer.productos_to_proveedores(productos)
        
        logger.info(f"📦 Proveedores únicos encontrados: {len(proveedores)}")
        if proveedores:
            top_3 = proveedores[:3]
            logger.info(f"🏆 Top 3 proveedores: {[p['proveedor'] for p in top_3]}")
        
        return productos, proveedores
    
    def buscar_proveedores_con_relevancia(
        self,
        product: str,
        top_k: int = 25,
        marca_filtro: Optional[str] = None
    ) -> Tuple[List[ProveedorInfo], str, List[str]]:
        """
        Búsqueda con sistema de umbrales escalonados + filtrado inteligente con LLM.
        
        Args:
            product: Nombre del producto a buscar
            top_k: Número máximo de productos a retornar
            marca_filtro: Marca específica para filtrar (opcional)
            
        Returns:
            Tuple de (proveedores, nivel_relevancia, marcas_disponibles)
        """
        logger.info(
            f"🎯 Búsqueda con relevancia escalonada + filtrado LLM para: '{product}'" +
            (f" | Marca: '{marca_filtro}'" if marca_filtro else "")
        )
        
        # NIVEL 1: Umbrales altos (coincidencia directa)
        productos_high, _ = self.buscar_productos_mejorado(
            search_query=product,
            top_k=top_k,
            threshold_trgm=settings.THRESHOLD_TRGM_HIGH,
            threshold_vector=settings.THRESHOLD_VEC_HIGH,
        )
        
        # Aplicar filtro de marca si se especificó
        if marca_filtro:
            marca_lower = marca_filtro.lower().strip()
            productos_high = [
                p for p in productos_high
                if p.get("marca") and p["marca"].lower().strip() == marca_lower
            ]
            logger.info(f"🏷️  Filtro de marca '{marca_filtro}' aplicado: {len(productos_high)} productos")
        
        # Extraer marcas disponibles
        marcas_disponibles = self.transformer.extract_marcas(productos_high)
        
        # Verificar productos con umbrales altos
        productos_relevantes_high = [
            p for p in productos_high
            if p["similaridad_trgm"] >= settings.THRESHOLD_TRGM_HIGH or
               p["similaridad_vector"] >= settings.THRESHOLD_VEC_HIGH
        ]
        
        if productos_relevantes_high:
            logger.info(
                f"✅ NIVEL 1 (ALTA): {len(productos_relevantes_high)} productos encontrados con alta relevancia"
            )
            logger.info(
                f"   Mejores similitudes: "
                f"Trgm={max(p['similaridad_trgm'] for p in productos_relevantes_high):.3f}, "
                f"Vec={max(p['similaridad_vector'] for p in productos_relevantes_high):.3f}"
            )
            
            # Aplicar filtrado inteligente con LLM
            productos_filtrados = self.filter.filter_with_llm(productos_relevantes_high, product)
            
            if not productos_filtrados:
                logger.warning(f"⚠️  Filtrado LLM eliminó TODOS los productos de nivel ALTA - intentando nivel MEDIA")
            else:
                # Reagrupar por proveedor con contexto de precios
                salida = self.transformer.proveedores_con_precios(productos_filtrados)
                
                if not salida:
                    logger.warning(f"⚠️  No quedaron proveedores después del filtrado - intentando nivel MEDIA")
                else:
                    return salida, RelevanciaLevel.ALTA.value, marcas_disponibles
        
        # NIVEL 2: Umbrales medios (productos similares/alternativos)
        logger.info(f"⚠️  NIVEL 1 no cumplido, intentando NIVEL 2 (MEDIA)...")
        
        productos_med, _ = self.buscar_productos_mejorado(
            search_query=product,
            top_k=top_k,
            threshold_trgm=settings.THRESHOLD_TRGM_MED,
            threshold_vector=settings.THRESHOLD_VEC_MED,
        )
        
        # Aplicar filtro de marca si se especificó
        if marca_filtro:
            marca_lower = marca_filtro.lower().strip()
            productos_med = [
                p for p in productos_med
                if p.get("marca") and p["marca"].lower().strip() == marca_lower
            ]
            logger.info(f"🏷️  Filtro de marca '{marca_filtro}' aplicado (nivel medio): {len(productos_med)} productos")
        
        # Extraer marcas disponibles si no se encontraron en nivel alto
        if not marcas_disponibles:
            marcas_disponibles = self.transformer.extract_marcas(productos_med)
        
        productos_relevantes_med = [
            p for p in productos_med
            if p["similaridad_trgm"] >= settings.THRESHOLD_TRGM_MED or
               p["similaridad_vector"] >= settings.THRESHOLD_VEC_MED
        ]
        
        if productos_relevantes_med:
            logger.info(
                f"⚡ NIVEL 2 (MEDIA): {len(productos_relevantes_med)} productos similares encontrados"
            )
            logger.info(
                f"   Mejores similitudes: "
                f"Trgm={max(p['similaridad_trgm'] for p in productos_relevantes_med):.3f}, "
                f"Vec={max(p['similaridad_vector'] for p in productos_relevantes_med):.3f}"
            )
            
            # Aplicar filtrado inteligente con LLM
            productos_filtrados = self.filter.filter_with_llm(productos_relevantes_med, product)
            
            if not productos_filtrados:
                logger.warning(f"⚠️  Filtrado LLM eliminó TODOS los productos de nivel MEDIA")
                return [], RelevanciaLevel.NULA.value, []
            
            salida = self.transformer.proveedores_con_precios(productos_filtrados)
            
            if not salida:
                logger.warning(f"⚠️  No quedaron proveedores después del filtrado nivel MEDIA")
                return [], RelevanciaLevel.NULA.value, []
            
            return salida, RelevanciaLevel.MEDIA.value, marcas_disponibles
        
        # NIVEL 3: Sin coincidencias relevantes
        logger.warning(f"❌ NIVEL 3 (NULA): No se encontraron productos relevantes para '{product}'")
        return [], RelevanciaLevel.NULA.value, []
    
    def obtener_detalle_proveedor(self, proveedor_id: int) -> Optional[dict]:
        """
        Obtiene el detalle de contacto de un proveedor por id.
        
        Args:
            proveedor_id: ID del proveedor
            
        Returns:
            Diccionario con información de contacto o None
        """
        from chat.services.whatsapp_formatter import WhatsAppFormatter
        
        row = self.db.get_proveedor_detalle(proveedor_id)
        
        if not row:
            return None
        
        numeros, links = WhatsAppFormatter.format_numbers(row.whatsapp_ventas)
        
        return {
            "proveedor_id": row.id_proveedor,
            "proveedor": row.nombre_comercial,
            "nombre_ejecutivo_ventas": row.nombre_ejecutivo_ventas,
            "whatsapp_ventas_list": numeros,
            "whatsapp_links": links,
            "pagina_web": row.pagina_web,
        }
    
    def obtener_marcas_disponibles(self, product: str, top_k: int = 50) -> List[str]:
        """
        Obtiene las marcas disponibles para un producto dado.
        
        Args:
            product: Nombre del producto
            top_k: Número máximo de productos a buscar
            
        Returns:
            Lista de marcas únicas ordenadas alfabéticamente
        """
        logger.info(f"🏷️  ═══════════════════════════════════════════════════════")
        logger.info(f"🏷️  OBTENER MARCAS DISPONIBLES")
        logger.info(f"🔍 Producto solicitado: '{product}'")
        logger.info(f"📊 Top_k configurado: {top_k}")
        
        # Búsqueda con umbrales bajos para capturar todas las variantes
        productos, _ = self.buscar_productos_mejorado(
            search_query=product,
            top_k=top_k,
            threshold_trgm=0.40,
            threshold_vector=0.70,
        )
        
        logger.info(f"📦 Productos obtenidos de la búsqueda: {len(productos)}")
        
        # Extraer marcas únicas
        marcas_lista = self.transformer.extract_marcas(productos)
        
        productos_con_marca = sum(1 for p in productos if p.get("marca"))
        productos_sin_marca = len(productos) - productos_con_marca
        
        logger.info(f"📊 Estadísticas de marcas:")
        logger.info(f"   • Productos con marca válida: {productos_con_marca}")
        logger.info(f"   • Productos sin marca: {productos_sin_marca}")
        logger.info(f"✅ Total de marcas únicas encontradas: {len(marcas_lista)}")
        
        if marcas_lista:
            logger.info(f"🏷️  Primeras 5 marcas: {marcas_lista[:5]}")
        else:
            logger.warning(f"⚠️  No se encontraron marcas para '{product}'")
        
        logger.info(f"🏷️  ═══════════════════════════════════════════════════════")
        
        return marcas_lista
