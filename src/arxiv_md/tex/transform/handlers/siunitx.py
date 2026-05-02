from __future__ import annotations

from arxiv_md.tex.ast import Command, Group, Text
from arxiv_md.tex.handler_types import CommandHandler, TransformContextProtocol
from arxiv_md.tex.model import InlineNode, TextSpan

__all__ = [
    "SIUNITX_COMMANDS",
    "handle_SI",
    "handle_si",
    "handle_ang",
    "handle_num",
    "handle_SIrange",
]


_PREFIXES: dict[str, str] = {
    "yocto": "y",
    "zepto": "z",
    "atto": "a",
    "femto": "f",
    "pico": "p",
    "nano": "n",
    "micro": "µ",
    "milli": "m",
    "centi": "c",
    "deci": "d",
    "deca": "da",
    "hecto": "h",
    "kilo": "k",
    "mega": "M",
    "giga": "G",
    "tera": "T",
    "peta": "P",
    "exa": "E",
    "zetta": "Z",
    "yotta": "Y",
}


_UNITS: dict[str, str] = {
    "meter": "m",
    "metre": "m",
    "kilogram": "kg",
    "gram": "g",
    "second": "s",
    "ampere": "A",
    "kelvin": "K",
    "mole": "mol",
    "candela": "cd",
    "hertz": "Hz",
    "newton": "N",
    "pascal": "Pa",
    "joule": "J",
    "watt": "W",
    "coulomb": "C",
    "volt": "V",
    "farad": "F",
    "ohm": "Ω",
    "siemens": "S",
    "weber": "Wb",
    "tesla": "T",
    "henry": "H",
    "lumen": "lm",
    "lux": "lx",
    "becquerel": "Bq",
    "gray": "Gy",
    "sievert": "Sv",
    "katal": "kat",
    "liter": "L",
    "litre": "L",
    "electronvolt": "eV",
    "byte": "B",
    "bit": "bit",
    "bar": "bar",
    "angstrom": "Å",
    "degree": "°",
    "arcminute": "′",
    "arcsecond": "″",
    "percent": "%",
    "dB": "dB",
    "decibel": "dB",
}


_MODIFIERS: dict[str, str] = {
    "per": "/",
    "squared": "²",
    "cubed": "³",
    "square": "²",
    "cubic": "³",
    "tothe": "",
    "raiseto": "",
    "of": "",
}


def _resolve_unit_nodes(nodes: list) -> str:
    parts: list[str] = []
    i = 0
    while i < len(nodes):
        node = nodes[i]
        if isinstance(node, Command):
            name = node.name
            if name in _PREFIXES:
                parts.append(_PREFIXES[name])
            elif name in _UNITS:
                parts.append(_UNITS[name])
            elif name in _MODIFIERS:
                sym = _MODIFIERS[name]
                if sym:
                    parts.append(sym)

                if name in ("tothe", "raiseto") and node.args:
                    exp = _nodes_to_text(list(node.args[0].children))
                    _superscript = {"2": "²", "3": "³", "4": "⁴"}
                    parts.append(_superscript.get(exp, f"^{exp}"))
            elif name == "cancel":
                pass
            else:
                parts.append(name)

            if node.args:
                for arg in node.args:
                    arg_text = _nodes_to_text(list(arg.children))
                    if arg_text:
                        parts.append(arg_text)
        elif isinstance(node, Text):
            val = node.value.strip()
            if val:
                parts.append(val)
        elif isinstance(node, Group):
            parts.append(_resolve_unit_nodes(list(node.children)))
        i += 1
    return "".join(parts)


def _nodes_to_text(nodes: list) -> str:
    parts: list[str] = []
    for n in nodes:
        if isinstance(n, Text):
            parts.append(n.value)
        elif isinstance(n, Command):
            if n.name in _PREFIXES:
                parts.append(_PREFIXES[n.name])
            elif n.name in _UNITS:
                parts.append(_UNITS[n.name])
            elif n.name in _MODIFIERS and _MODIFIERS[n.name]:
                parts.append(_MODIFIERS[n.name])
            else:
                parts.append(n.name)
        elif isinstance(n, Group):
            parts.append(_nodes_to_text(list(n.children)))
    return "".join(parts)


def _get_arg_children(cmd: Command, idx: int) -> list:
    if idx < len(cmd.args):
        return list(cmd.args[idx].children)
    return []


def handle_SI(cmd: Command, ctx: TransformContextProtocol) -> list[InlineNode]:
    value_nodes = _get_arg_children(cmd, 0)
    unit_nodes = _get_arg_children(cmd, 1)

    value = _nodes_to_text(value_nodes).strip()
    unit = _resolve_unit_nodes(unit_nodes).strip()

    if value and unit:
        return [TextSpan(text=f"{value}\u202f{unit}")]
    if value:
        return [TextSpan(text=value)]
    if unit:
        return [TextSpan(text=unit)]
    return []


def handle_si(cmd: Command, ctx: TransformContextProtocol) -> list[InlineNode]:
    unit_nodes = _get_arg_children(cmd, 0)
    unit = _resolve_unit_nodes(unit_nodes).strip()
    return [TextSpan(text=unit)] if unit else []


def handle_ang(cmd: Command, ctx: TransformContextProtocol) -> list[InlineNode]:
    arg_nodes = _get_arg_children(cmd, 0)
    raw = _nodes_to_text(arg_nodes).strip()
    if ";" in raw:
        parts = raw.split(";")
        result = ""
        symbols = ["°", "′", "″"]
        for p, sym in zip(parts, symbols):
            p = p.strip()
            if p:
                result += f"{p}{sym}"
        return [TextSpan(text=result)] if result else []
    return [TextSpan(text=f"{raw}°")] if raw else []


def handle_num(cmd: Command, ctx: TransformContextProtocol) -> list[InlineNode]:
    arg_nodes = _get_arg_children(cmd, 0)
    raw = _nodes_to_text(arg_nodes).strip()
    if not raw:
        return []

    import re

    m = re.match(r"^([^eE]+)[eE]([+-]?\d+)$", raw)
    if m:
        mantissa = m.group(1).strip()
        exp = m.group(2).strip()

        sup_map = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
        sup = exp.translate(sup_map)
        return [TextSpan(text=f"{mantissa} × 10{sup}")]

    return [TextSpan(text=raw)]


def handle_SIrange(cmd: Command, ctx: TransformContextProtocol) -> list[InlineNode]:
    lo_nodes = _get_arg_children(cmd, 0)
    hi_nodes = _get_arg_children(cmd, 1)
    unit_nodes = _get_arg_children(cmd, 2)

    lo = _nodes_to_text(lo_nodes).strip()
    hi = _nodes_to_text(hi_nodes).strip()
    unit = _resolve_unit_nodes(unit_nodes).strip()

    if unit:
        return [TextSpan(text=f"{lo}\u202f{unit} to {hi}\u202f{unit}")]
    return [TextSpan(text=f"{lo} to {hi}")]


SIUNITX_COMMANDS: dict[str, CommandHandler] = {
    "SI": handle_SI,
    "si": handle_si,
    "ang": handle_ang,
    "num": handle_num,
    "SIrange": handle_SIrange,
    "numrange": handle_SIrange,
}
