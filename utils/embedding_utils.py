import os
import logging
from openai import OpenAI

# Carga la API key desde variables de entorno
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key)

def generar_embedding(texto: str) -> list:
    """
    Genera un embedding desde un string usando OpenAI.

    Args:
        texto (str): Texto para embebido.

    Returns:
        list: Vector de embedding o None si falla.
    """
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-ada-002",
            input=texto.strip().replace("\n", " ")
        )
        return response.data[0].embedding
    except Exception as e:
        logging.error(f"Error generando embedding para '{texto}': {e}")
        return None
