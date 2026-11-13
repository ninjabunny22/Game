"""Writes the overlay's icons as small flat SVGs into godot/assets/icons, in the packs' warm,
flat colours. Run from the repository root:

    python3 tools/make_icons.py

Each icon is drawn on a 24 x 24 grid in one light colour (with an accent where it helps), so
it reads on the overlay's dark panels at button size.
"""

import os

OUT = os.path.join(os.path.dirname(__file__), "..", "godot", "assets", "icons")
INK = "#f4ead5"  # the light glyph colour
GOLD = "#e8b84a"
RED = "#e0533f"
BLUE = "#59a6ff"
GREEN = "#59c866"
GREY = "#aaaaaa"
STEEL = "#d8dde3"
WOOD = "#b5763a"

ICONS = {
    "pause": f'<rect x="6" y="5" width="4" height="14" rx="1" fill="{INK}"/><rect x="14" y="5" width="4" height="14" rx="1" fill="{INK}"/>',
    "play": f'<path d="M7 4.5 L19 12 L7 19.5 Z" fill="{INK}"/>',
    "step": f'<path d="M5 5 L14 12 L5 19 Z" fill="{INK}"/><rect x="16" y="5" width="3" height="14" rx="1" fill="{INK}"/>',
    "slower": f'<path d="M12 6 L4 12 L12 18 Z" fill="{INK}"/><path d="M20 6 L12 12 L20 18 Z" fill="{INK}"/>',
    "faster": f'<path d="M4 6 L12 12 L4 18 Z" fill="{INK}"/><path d="M12 6 L20 12 L12 18 Z" fill="{INK}"/>',
    # Diplomacy: two pennants, crossed, in war red and alliance blue.
    "diplomacy": (f'<rect x="5" y="3" width="1.8" height="18" rx="0.9" fill="{INK}" transform="rotate(-12 6 12)"/>'
                  f'<path d="M7 4 L15 6.5 L7 9.5 Z" fill="{RED}" transform="rotate(-12 6 12)"/>'
                  f'<rect x="17.2" y="3" width="1.8" height="18" rx="0.9" fill="{INK}" transform="rotate(12 18 12)"/>'
                  f'<path d="M17 4 L9 6.5 L17 9.5 Z" fill="{BLUE}" transform="rotate(12 18 12)"/>'),
    "help": (f'<circle cx="12" cy="12" r="9" fill="none" stroke="{INK}" stroke-width="2"/>'
             f'<path d="M9.2 9.5 Q9.4 6.6 12.2 6.6 Q15 6.7 15 9.2 Q15 11 12.8 11.9 Q12 12.3 12 13.6" '
             f'fill="none" stroke="{INK}" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="17" r="1.3" fill="{INK}"/>'),
    # Back to the menu: a castle gate.
    "menu": (f'<path d="M4 20 V8 H6.5 V10 H9 V8 H11.5 V10 H12.5 V8 H15 V10 H17.5 V8 H20 V20 Z" fill="{INK}"/>'
             f'<path d="M9.5 20 V15.5 Q12 12.5 14.5 15.5 V20 Z" fill="#3a3530"/>'),
    "legend": (f'<rect x="4" y="5.5" width="16" height="2.4" rx="1.2" fill="{RED}"/>'
               f'<rect x="4" y="10.5" width="16" height="2.4" rx="1.2" fill="{BLUE}"/>'
               f'<rect x="4" y="15.5" width="16" height="2.4" rx="1.2" fill="{GREEN}"/>'),
    # The tech tree: three nodes branching from a root.
    "tech": (f'<path d="M12 18 V12 M12 12 L6 7 M12 12 L18 7 M12 12 V6" stroke="{INK}" stroke-width="1.8" fill="none"/>'
             f'<circle cx="12" cy="19" r="2.4" fill="{GOLD}"/><circle cx="6" cy="6.5" r="2.2" fill="{INK}"/>'
             f'<circle cx="12" cy="5" r="2.2" fill="{INK}"/><circle cx="18" cy="6.5" r="2.2" fill="{INK}"/>'),
    # A battle: two crossed swords.
    "battle": (f'<path d="M5 4 L16 15" stroke="{STEEL}" stroke-width="2.4" stroke-linecap="round"/>'
               f'<path d="M19 4 L8 15" stroke="{STEEL}" stroke-width="2.4" stroke-linecap="round"/>'
               f'<path d="M13.5 17.5 L18.5 12.5 M5.5 12.5 L10.5 17.5" stroke="{GOLD}" stroke-width="2" stroke-linecap="round"/>'
               f'<path d="M17 16 L20 19 M7 16 L4 19" stroke="{WOOD}" stroke-width="2.4" stroke-linecap="round"/>'),
    # A native stronghold: a shield with a band across it.
    "shield": (f'<path d="M12 3 L20 6 V12 Q20 18 12 21.5 Q4 18 4 12 V6 Z" fill="{GREY}" stroke="{INK}" stroke-width="1.6"/>'
               f'<path d="M4.6 10 H19.4 V13 H4.6 Z" fill="{WOOD}"/>'),
    # Map layers: region borders (a dashed outline), the lines between castles, deposits (a gem).
    "borders": (f'<path d="M4 6 L11 4 L20 7 L19 17 L12 20 L5 16 Z" fill="none" stroke="{INK}" stroke-width="2" '
                f'stroke-dasharray="3 2" stroke-linejoin="round"/>'),
    "lines": (f'<path d="M4 18 Q12 2 20 18" fill="none" stroke="{RED}" stroke-width="2.2" stroke-linecap="round"/>'
              f'<path d="M4 18 Q12 9 20 18" fill="none" stroke="{BLUE}" stroke-width="2.2" stroke-linecap="round"/>'
              f'<circle cx="4" cy="18" r="2" fill="{INK}"/><circle cx="20" cy="18" r="2" fill="{INK}"/>'),
    "resources": (f'<path d="M7 5 H17 L21 10 L12 20 L3 10 Z" fill="{GOLD}"/>'
                  f'<path d="M3 10 H21 M9 5 L12 10 L15 5 M12 10 L12 20" stroke="#8a6a1f" stroke-width="1.1" fill="none"/>'),
    "close": f'<path d="M6 6 L18 18 M18 6 L6 18" stroke="{INK}" stroke-width="2.4" stroke-linecap="round"/>',
}


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for name, body in ICONS.items():
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24">{body}</svg>\n'
        with open(os.path.join(OUT, name + ".svg"), "w") as handle:
            handle.write(svg)
    print(f"{len(ICONS)} icons in {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
