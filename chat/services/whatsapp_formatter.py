"""Utilidades para WhatsApp - Single Responsibility Principle."""
import re
from typing import Tuple, List


class WhatsAppFormatter:
    """Formateador de números de WhatsApp."""
    
    _SEP_SPLIT = re.compile(r"[,\n/;|]+")
    _DIGITS = re.compile(r"\D+")
    
    @classmethod
    def format_numbers(cls, raw: str | None, default_cc: str = "52") -> Tuple[List[str], List[str]]:
        """
        Devuelve (numeros_limpios, links_wa) deduplicados manteniendo el orden.
        
        Args:
            raw: Cadena con números separados por comas, saltos de línea, etc.
            default_cc: Código de país por defecto (52 para México)
            
        Returns:
            Tuple de (números normalizados, enlaces wa.me)
        """
        uniq, links, seen = [], [], set()
        for token in cls._split_phones(raw):
            d = cls._only_digits(token)
            d = cls._normalize_with_cc(d, default_cc=default_cc)
            if not d or d in seen:
                continue
            seen.add(d)
            uniq.append(d)
            links.append(f"https://wa.me/{d}")
        return uniq, links
    
    @classmethod
    def _split_phones(cls, raw: str | None) -> List[str]:
        """Separa por separadores comunes y limpia espacios."""
        if not raw:
            return []
        return [t.strip() for t in cls._SEP_SPLIT.split(raw) if t.strip()]
    
    @classmethod
    def _only_digits(cls, s: str) -> str:
        """Deja solo dígitos."""
        return cls._DIGITS.sub("", s or "")
    
    @classmethod
    def _normalize_with_cc(cls, digits: str, default_cc: str = "52") -> str:
        """
        Normaliza para wa.me:
        - Si ya trae prefijo país (52 o 521) lo respeta.
        - Si no lo trae y parece local (>=10 dígitos), antepone default_cc.
        - Si es demasiado corto, lo deja tal cual.
        """
        if not digits:
            return ""
        if digits.startswith("52") or digits.startswith("521"):
            return digits
        if len(digits) >= 10:
            return default_cc + digits
        return digits
