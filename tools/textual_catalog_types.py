"""Curated CSS type metadata for the Textual skill generator."""

CSS_TYPES = {
    "border": {"name": "<border>", "summary": "Border edge, line style, and colour shorthand.", "grammar": "edge | style | colour, or a combination", "consumers": "border, outline", "example": "border: solid $primary;"},
    "color": {"name": "<color>", "summary": "A named theme colour, hex colour, rgb(), hsl(), or $variable.", "grammar": "name | #rrggbb | #rrggbbaa | rgb(...) | hsl(...) | $variable", "consumers": "color, background, border, outline, tint, scrollbar-*", "example": "color: $text-muted;"},
    "hatch": {"name": "<hatch>", "summary": "A repeating hatch pattern with an optional colour.", "grammar": "hatch-name [colour]", "consumers": "hatch", "example": "hatch: cross $primary;"},
    "horizontal": {"name": "<horizontal>", "summary": "Horizontal alignment keyword.", "grammar": "left | center | right", "consumers": "align, content-align", "example": "align-horizontal: center;"},
    "integer": {"name": "<integer>", "summary": "A whole number, optionally signed.", "grammar": "[+-]?[0-9]+", "consumers": "column-span, row-span, grid-size", "example": "column-span: 2;"},
    "keyline": {"name": "<keyline>", "summary": "A keyline edge and colour.", "grammar": "edge colour", "consumers": "keyline", "example": "keyline: thick $accent;"},
    "name": {"name": "<name>", "summary": "An identifier used for layers, ids, and classes.", "grammar": "[a-zA-Z_-][a-zA-Z0-9_-]*", "consumers": "layer, layers, class names", "example": "layer: overlay;"},
    "number": {"name": "<number>", "summary": "A floating-point number.", "grammar": "[+-]?[0-9]*\\.?[0-9]+", "consumers": "opacity, text-opacity, tint", "example": "opacity: 0.8;"},
    "overflow": {"name": "<overflow>", "summary": "Overflow handling for one or both axes.", "grammar": "hidden | scroll | auto", "consumers": "overflow", "example": "overflow: auto;"},
    "pointer": {"name": "<pointer>", "summary": "A mouse cursor shape name.", "grammar": "default | pointer | text | crosshair | move | not-allowed | ...", "consumers": "pointer", "example": "pointer: pointer;"},
    "position": {"name": "<position>", "summary": "Normal-flow or absolute positioning.", "grammar": "relative | absolute", "consumers": "position", "example": "position: absolute;"},
    "percentage": {"name": "<percentage>", "summary": "A percentage of the containing dimension.", "grammar": "[0-9]+%", "consumers": "width, height, offset, margin, padding", "example": "width: 50%;"},
    "scalar": {"name": "<scalar>", "summary": "A cell count, fraction, percentage, or auto keyword.", "grammar": "integer | numberfr | percentage | auto", "consumers": "width, height, min/max, margin, padding, offset", "example": "height: 1fr;"},
    "text_align": {"name": "<text-align>", "summary": "Text alignment keyword.", "grammar": "left | center | right | justify", "consumers": "text-align", "example": "text-align: center;"},
    "text_style": {"name": "<text-style>", "summary": "One or more text decorations.", "grammar": "bold | italic | underline | reverse | strike | none, combinable", "consumers": "text-style, link-style, border-title-style", "example": "text-style: bold underline;"},
    "vertical": {"name": "<vertical>", "summary": "Vertical alignment keyword.", "grammar": "top | middle | bottom", "consumers": "align, content-align", "example": "align-vertical: middle;"},
}
