"""Shared HTML post-processing for anything that produces email/template HTML
from an external source (Word import, the drag-and-drop email builder) and
needs a single self-contained fragment — CSS inlined, no <style>/<head>."""
import re


def prune_style_block(html: str) -> str:
    """Keep only class-qualified CSS rules (e.g. h1.western { color: ... }).

    Bare tag-selector rules (e.g. a blanket `p { text-align: start }`) would,
    if inlined naively, override more specific per-element attributes an
    individual element already has (e.g. a genuinely centered paragraph's
    align="center"). Dropping bare tag-selector rules and keeping only
    class-qualified ones avoids that clobbering.
    """
    def _filter(m: re.Match) -> str:
        css = m.group(1)
        rules = re.findall(r'([^{}]+)\{([^{}]*)\}', css)
        kept = [f"{sel.strip()} {{{body}}}" for sel, body in rules if '.' in sel]
        return '<style type="text/css">' + '\n'.join(kept) + '</style>'
    return re.sub(r'<style[^>]*>([\s\S]*?)</style>', _filter, html, flags=re.IGNORECASE)


def inline_and_extract_body(html: str) -> str:
    """Inline any <style> block CSS into element style="" attributes and
    return just the <body> contents, for use as a standalone HTML fragment."""
    from premailer import Premailer
    pruned = prune_style_block(html)
    inlined = Premailer(pruned, keep_style_tags=False, remove_classes=True,
                         cssutils_logging_level="CRITICAL").transform()
    m = re.search(r'<body[^>]*>([\s\S]*?)</body>', inlined, re.IGNORECASE)
    return (m.group(1) if m else inlined).strip()
