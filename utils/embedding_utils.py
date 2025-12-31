import os
import logging
from openai import OpenAI

# Carga la API key desde variables de entorno
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key)

def generar_embedding(texto: str) -> list:
    """
    Genera un embedding desde un string usando OpenAI.
    
    ⚠️ TEMPORALMENTE DESHABILITADO: Retorna None para evitar errores de quota.
    TODO: Restaurar cuando tengas una API key válida con crédito.

    Args:
        texto (str): Texto para embebido.

    Returns:
        list: Vector de embedding o None si falla.
    """
    # TEMPORALMENTE DESHABILITADO - Sin quota en OpenAI
    logging.debug(f"⚠️ Embedding deshabilitado temporalmente para: '{texto[:50]}...'")
    return None
    
    # TODO: Descomentar cuando tengas API key válida
    # try:
    #     if texto is None:
    #         return None
    #
    #     # Saneado robusto de entrada (evita errores con floats/None)
    #     s = str(texto).strip().replace("\n", " ")
    #     if not s:
    #         return None
    #
    #     response = openai_client.embeddings.create(
    #         model="text-embedding-ada-002",
    #         input=s
    #     )
    #     return response.data[0].embedding
    # except Exception as e:
    #     logging.error(f"Error generando embedding para '{texto}': {e}")
    #     return None
