"""
DataScheduler — ui/components/
Composants partagés par plusieurs écrans (refonte, FONDATIONS.md section 3). Un seul endroit à
faire évoluer plutôt qu'une réimplémentation par vue. Construits au fil des lots qui en ont
réellement besoin — voir docs/refonte/impact/0a.md et a-parametres.md.
"""

from ui.components.page_header import make_page_header
from ui.components.info_pill import make_info_pill

__all__ = ["make_page_header", "make_info_pill"]
