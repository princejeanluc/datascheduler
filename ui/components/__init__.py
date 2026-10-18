"""
DataScheduler — ui/components/
Composants partagés par plusieurs écrans (refonte, FONDATIONS.md section 3). Un seul endroit à
faire évoluer plutôt qu'une réimplémentation par vue. Construits au fil des lots qui en ont
réellement besoin — voir docs/refonte/impact/0a.md : seul l'en-tête de page est posé au lot 0a
(spécifié au pixel dans FONDATIONS.md sections 1/2, sans écran consommateur nécessaire pour le
valider), les autres composants listés dans FONDATIONS.md section 3 arrivent avec le premier
Lot A qui en a besoin.
"""

from ui.components.page_header import make_page_header

__all__ = ["make_page_header"]
