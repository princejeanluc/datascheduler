"""
DataScheduler — ui/components/
Composants partagés par plusieurs écrans (refonte, FONDATIONS.md section 3). Un seul endroit à
faire évoluer plutôt qu'une réimplémentation par vue. Construits au fil des lots qui en ont
réellement besoin — voir docs/refonte/impact/0a.md et a-parametres.md.
"""

from ui.components.page_header import make_page_header
from ui.components.info_pill import make_info_pill
from ui.components.banner import make_banner
from ui.components.switch import Switch, make_switch
from ui.components.side_panel import SidePanel

__all__ = [
    "make_page_header", "make_info_pill", "make_banner", "Switch", "make_switch", "SidePanel",
]
