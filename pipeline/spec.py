"""
Estructuras compartidas: Slide y PostSpec.

Vivían dentro del renderer de Pillow. Al reemplazarlo por el motor HTML se
sacaron acá para que `generate.py`, `site.py` y `render_html.py` no dependan
de un renderer concreto.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Stat:
    """Una cifra con su etiqueta. Es lo que va en las tarjetas .stat."""
    number: str
    label: str
    source: str = ""


@dataclass
class Slide:
    """
    Un frame del carrusel. Tres roles, según el brand guide:
    `hook` (gancho, oscuro) · `data` (cifras, claro) · `close` (cierre, oscuro).
    """
    role: str
    headline: str
    body: str = ""
    accent: str = ""                 # parte del titular que va en cian
    source: str = ""
    kicker: str = ""
    stat: str = ""                   # cifra grande del hook
    stats: list[Stat] = field(default_factory=list)   # tarjetas del slide de datos
    # Alternativa a `stats` cuando el post no tiene cifras: líneas de texto
    # aprobado. Nueve de los quince bloques evergreen no traen datos, y sin
    # esto su segundo frame salía con un título y nada más.
    bullets: list[str] = field(default_factory=list)
    chain: str = ""                  # el ciclo DentRead, solo en el cierre


@dataclass
class PostSpec:
    slug: str
    slides: list[Slide]
    caption_es: str
    commentary_en: str
    title_en: str
    citations: list[str] = field(default_factory=list)
    mode: str = "data"
    declarations: dict = field(default_factory=dict)
    # "modelo" si los titulares los escribió el modelo y cruzaron los
    # controles, "curada" si se cayó a la versión del catálogo. Queda en
    # post.json para poder auditar después de qué lado salió cada publicación.
    redaccion: str = "curada"
