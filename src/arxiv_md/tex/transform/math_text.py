from __future__ import annotations

import re
from typing import Callable


MathCommandHandler = Callable[[str, int, str], tuple[str | None, int]]


_MATH_UNICODE: dict[str, str] = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "varepsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "vartheta": "ϑ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "pi": "π",
    "varpi": "ϖ",
    "rho": "ρ",
    "varrho": "ϱ",
    "sigma": "σ",
    "varsigma": "ς",
    "tau": "τ",
    "upsilon": "υ",
    "phi": "φ",
    "varphi": "ϕ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "Alpha": "Α",
    "Beta": "Β",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Epsilon": "Ε",
    "Zeta": "Ζ",
    "Eta": "Η",
    "Theta": "Θ",
    "Iota": "Ι",
    "Kappa": "Κ",
    "Lambda": "Λ",
    "Mu": "Μ",
    "Nu": "Ν",
    "Xi": "Ξ",
    "Pi": "Π",
    "Rho": "Ρ",
    "Sigma": "Σ",
    "Tau": "Τ",
    "Upsilon": "Υ",
    "Phi": "Φ",
    "Chi": "Χ",
    "Psi": "Ψ",
    "Omega": "Ω",
    "pm": "±",
    "mp": "∓",
    "times": "×",
    "div": "÷",
    "cdot": "·",
    "ast": "∗",
    "infty": "∞",
    "leq": "≤",
    "le": "≤",
    "geq": "≥",
    "ge": "≥",
    "neq": "≠",
    "ne": "≠",
    "approx": "≈",
    "sim": "∼",
    "propto": "∝",
    "equiv": "≡",
    "triangleq": "≜",
    "subset": "⊂",
    "supset": "⊃",
    "subseteq": "⊆",
    "supseteq": "⊇",
    "cup": "∪",
    "cap": "∩",
    "in": "∈",
    "notin": "∉",
    "emptyset": "∅",
    "varnothing": "∅",
    "rightarrow": "→",
    "to": "→",
    "mapsto": "↦",
    "leftarrow": "←",
    "gets": "←",
    "Leftrightarrow": "⇔",
    "Rightarrow": "⇒",
    "Leftarrow": "⇐",
    "leftrightarrow": "↔",
    "uparrow": "↑",
    "downarrow": "↓",
    "updownarrow": "↕",
    "Uparrow": "⇑",
    "Downarrow": "⇓",
    "Updownarrow": "⇕",
    "longrightarrow": "⟶",
    "longleftarrow": "⟵",
    "longleftrightarrow": "⟷",
    "Longrightarrow": "⟹",
    "Longleftarrow": "⟸",
    "Longleftrightarrow": "⟺",
    "hookrightarrow": "↪",
    "hookleftarrow": "↩",
    "nearrow": "↗",
    "searrow": "↘",
    "swarrow": "↙",
    "nwarrow": "↖",
    "implies": "⇒",
    "iff": "⇔",
    "star": "⋆",
    "bullet": "•",
    "circ": "∘",
    "oplus": "⊕",
    "ominus": "⊖",
    "otimes": "⊗",
    "odot": "⊙",
    "setminus": "∖",
    "ll": "≪",
    "gg": "≫",
    "prec": "≺",
    "succ": "≻",
    "preceq": "⪯",
    "succeq": "⪰",
    "sqcap": "⊓",
    "sqcup": "⊔",
    "models": "⊨",
    "vdash": "⊢",
    "dashv": "⊣",
    "aleph": "ℵ",
    "beth": "ℶ",
    "Box": "□",
    "Diamond": "◇",
    "checkmark": "✓",
    "Checkmark": "✓",
    "copyright": "©",
    "degree": "°",
    "ldotp": ".",
    "cdotp": "·",
    "colon": ":",
    "semicolon": ";",
    "forall": "∀",
    "exists": "∃",
    "neg": "¬",
    "lnot": "¬",
    "wedge": "∧",
    "land": "∧",
    "vee": "∨",
    "lor": "∨",
    "sum": "∑",
    "prod": "∏",
    "int": "∫",
    "oint": "∮",
    "partial": "∂",
    "nabla": "∇",
    "sqrt": "√",
    "dagger": "†",
    "ddagger": "‡",
    "ldots": "…",
    "cdots": "⋯",
    "vdots": "⋮",
    "ddots": "⋱",
    "prime": "′",
    "ell": "ℓ",
    "hbar": "ℏ",
    "Re": "ℜ",
    "Im": "ℑ",
    "top": "⊤",
    "bot": "⊥",
    "perp": "⊥",
    "angle": "∠",
    "triangle": "△",
    "square": "□",
    "langle": "⟨",
    "rangle": "⟩",
    "lceil": "⌈",
    "rceil": "⌉",
    "lfloor": "⌊",
    "rfloor": "⌋",
    "vert": "|",
    "Vert": "‖",
    "|": "‖",
}
_MATH_UNICODE_RE = re.compile(r"^\s*\\([A-Za-z]+)\s*$")


_SUPERSCRIPT_MAP: dict[str, str] = {
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
    "+": "⁺",
    "-": "⁻",
    "=": "⁼",
    "(": "⁽",
    ")": "⁾",
    "n": "ⁿ",
    "i": "ⁱ",
    "a": "ᵃ",
    "b": "ᵇ",
    "c": "ᶜ",
    "d": "ᵈ",
    "e": "ᵉ",
    "f": "ᶠ",
    "g": "ᵍ",
    "h": "ʰ",
    "j": "ʲ",
    "k": "ᵏ",
    "l": "ˡ",
    "m": "ᵐ",
    "o": "ᵒ",
    "p": "ᵖ",
    "r": "ʳ",
    "s": "ˢ",
    "t": "ᵗ",
    "u": "ᵘ",
    "v": "ᵛ",
    "w": "ʷ",
    "x": "ˣ",
    "y": "ʸ",
    "z": "ᶻ",
    "T": "ᵀ",
}
_SUBSCRIPT_MAP: dict[str, str] = {
    "0": "₀",
    "1": "₁",
    "2": "₂",
    "3": "₃",
    "4": "₄",
    "5": "₅",
    "6": "₆",
    "7": "₇",
    "8": "₈",
    "9": "₉",
    "+": "₊",
    "-": "₋",
    "=": "₌",
    "(": "₍",
    ")": "₎",
    "a": "ₐ",
    "e": "ₑ",
    "h": "ₕ",
    "i": "ᵢ",
    "j": "ⱼ",
    "k": "ₖ",
    "l": "ₗ",
    "m": "ₘ",
    "n": "ₙ",
    "o": "ₒ",
    "p": "ₚ",
    "r": "ᵣ",
    "s": "ₛ",
    "t": "ₜ",
    "u": "ᵤ",
    "v": "ᵥ",
    "x": "ₓ",
}


_SCRIPT_DISPATCH: dict[str, tuple[dict[str, str], str]] = {
    "^": (_SUPERSCRIPT_MAP, "sup"),
    "_": (_SUBSCRIPT_MAP, "sub"),
}


_MATH_TEXT_WRAPPERS: frozenset[str] = frozenset(
    {
        "mathrm",
        "text",
        "textrm",
        "textit",
        "textbf",
        "texttt",
        "textsf",
        "textsc",
        "textsl",
        "textmd",
        "textnormal",
        "emph",
        "mathbf",
        "mathsf",
        "mathtt",
        "mathit",
        "operatorname",
        "operatorname*",
        "boldsymbol",
        "bm",
        "mbox",
    }
)


_MATH_TEXT_DECLARATIONS: frozenset[str] = frozenset(
    {
        "small",
        "footnotesize",
        "scriptsize",
        "tiny",
        "large",
        "Large",
        "LARGE",
        "huge",
        "Huge",
        "normalsize",
        "bf",
        "it",
        "em",
        "tt",
        "rm",
        "sf",
        "sl",
        "sc",
        "bfseries",
        "itshape",
        "scshape",
        "upshape",
        "displaystyle",
        "textstyle",
        "scriptstyle",
        "scriptscriptstyle",
        "limits",
        "nolimits",
        "boldmath",
        "left",
        "right",
    }
)

_MATH_TEXT_MATRIX_ENVS: frozenset[str] = frozenset(
    {
        "array",
        "tabular",
        "matrix",
        "pmatrix",
        "bmatrix",
        "vmatrix",
        "Vmatrix",
        "Bmatrix",
        "smallmatrix",
    }
)
_MATH_TEXT_CASE_ENVS: frozenset[str] = frozenset({"cases"})
_MATH_TEXT_ALIGNED_ENVS: frozenset[str] = frozenset({"aligned", "gathered", "split"})
_MATH_TEXT_ENVS: frozenset[str] = (
    _MATH_TEXT_MATRIX_ENVS | _MATH_TEXT_CASE_ENVS | _MATH_TEXT_ALIGNED_ENVS
)
_MATH_TEXT_ENV_DELIMITERS: dict[str, tuple[str, str]] = {
    "pmatrix": ("(", ")"),
    "bmatrix": ("[", "]"),
    "vmatrix": ("|", "|"),
    "Vmatrix": ("‖", "‖"),
    "Bmatrix": ("{", "}"),
}
_MATH_LAYOUT_WRAPPERS: frozenset[str] = frozenset(
    {"smash", "mathclap", "mathllap", "mathrlap"}
)
_MATH_PHANTOM_COMMANDS: frozenset[str] = frozenset({"phantom", "hphantom", "vphantom"})
_MATH_ACCENT_COMMANDS: dict[str, str] = {
    "widetilde": "\u0303",
    "tilde": "\u0303",
    "widehat": "\u0302",
    "hat": "\u0302",
    "overline": "\u0304",
    "bar": "\u0304",
    "underline": "\u0332",
    "dot": "\u0307",
    "ddot": "\u0308",
    "vec": "\u20d7",
}


def _math_to_unicode(body: str) -> str | None:
    m = _MATH_UNICODE_RE.match(body)
    if not m:
        return None
    return _MATH_UNICODE.get(m.group(1))


def _read_command_name(body: str, pos: int, n: int) -> tuple[str | None, int]:
    j = pos
    while j < n and (body[j].isalpha() or body[j] == "@"):
        j += 1
    if j == pos:
        return None, pos
    return body[pos:j], j


def _handle_backslash_escape(body: str, pos: int, n: int) -> tuple[str, int] | None:
    if pos >= n:
        return None
    ch = body[pos]
    if ch in ",;!: ":
        return ("", pos + 1)
    if ch in "{}%#&":
        return (ch, pos + 1)
    return None


def _handle_begin(body: str, pos: int, _name: str) -> tuple[str | None, int]:
    return _render_math_environment(body, pos)


def _handle_end(_body: str, _pos: int, _name: str) -> tuple[str | None, int]:

    return None, 0


def _handle_layout_wrapper(body: str, pos: int, name: str) -> tuple[str | None, int]:
    return _render_layout_wrapper(body, pos, name)


def _handle_phantom(body: str, pos: int, _name: str) -> tuple[str | None, int]:
    end = _consume_discarded_braced_argument(body, pos)
    if end is None:
        return None, pos
    return "", end


def _handle_raisebox(body: str, pos: int, _name: str) -> tuple[str | None, int]:
    return _render_raisebox(body, pos)


def _handle_accent(body: str, pos: int, name: str) -> tuple[str | None, int]:
    return _render_accent_command(body, pos, name)


_MATH_TEXT_LOSSY_WRAPPERS: frozenset[str] = frozenset({"mathbb", "mathcal"})


def _handle_lossy_wrapper(_body: str, pos: int, _name: str) -> tuple[str | None, int]:
    return None, pos


def _handle_text_wrapper(body: str, pos: int, _name: str) -> tuple[str | None, int]:
    k = _skip_spaces(body, pos)
    n = len(body)
    if k < n and body[k] == "{":
        inner, end = _read_braced(body, k)
        if inner is None:
            return None, pos
        rendered = _math_to_text(inner)
        if rendered is None:
            return None, pos
        return rendered, end

    return "", pos


def _handle_declaration(body: str, pos: int, _name: str) -> tuple[str | None, int]:
    return "", _skip_spaces(body, pos)


def _handle_glyph(_body: str, pos: int, name: str) -> tuple[str | None, int]:
    return _MATH_UNICODE[name], pos


def _resolve_math_command(
    name: str,
) -> MathCommandHandler | None:

    if name == "begin":
        return _handle_begin
    if name == "end":
        return _handle_end
    if name in _MATH_LAYOUT_WRAPPERS:
        return _handle_layout_wrapper
    if name in _MATH_PHANTOM_COMMANDS:
        return _handle_phantom
    if name == "raisebox":
        return _handle_raisebox
    if name in _MATH_ACCENT_COMMANDS:
        return _handle_accent
    if name in _MATH_TEXT_LOSSY_WRAPPERS:
        return _handle_lossy_wrapper
    if name in _MATH_TEXT_WRAPPERS:
        return _handle_text_wrapper
    if name in _MATH_TEXT_DECLARATIONS:
        return _handle_declaration
    if name in _MATH_UNICODE:
        return _handle_glyph
    return None


def _handle_backslash_in_math(body: str, pos: int, n: int) -> tuple[str, int] | None:
    name, j = _read_command_name(body, pos, n)
    if name is None:
        return _handle_backslash_escape(body, pos, n)
    handler = _resolve_math_command(name)
    if handler is None:
        return None
    rendered, new_pos = handler(body, j, name)
    if rendered is None:
        return None
    return rendered, new_pos


def _render_braced_group(body: str, pos: int) -> tuple[str | None, int]:
    inner, end = _read_braced(body, pos)
    if inner is None:
        return None, pos
    rendered = _math_to_text(inner)
    if rendered is None:
        return None, pos
    return rendered, end


def _math_to_text(body: str) -> str | None:
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == "\\":
            result = _handle_backslash_in_math(body, i + 1, n)
            if result is None:
                return None
            text, i = result
            out.append(text)
            continue
        script = _SCRIPT_DISPATCH.get(ch)
        if script is not None:
            smap, tag = script
            next_i = _consume_script(body, i + 1, smap, out, html_tag=tag)
            if next_i is None:
                return None
            i = next_i
            continue
        if ch == "{":
            rendered, i = _render_braced_group(body, i)
            if rendered is None:
                return None
            out.append(rendered)
            continue
        if ch == "$":
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _render_layout_wrapper(
    text: str,
    pos: int,
    name: str,
) -> tuple[str | None, int]:
    k = _skip_spaces(text, pos)
    if name == "smash":
        after_square_args = _consume_square_args(text, k, max_count=1)
        if after_square_args is None:
            return None, pos
        k = after_square_args
    inner, end = _read_braced(text, k)
    if inner is None:
        return None, pos
    rendered = _math_to_text(inner)
    if rendered is None:
        return None, pos
    return rendered, end


def _consume_discarded_braced_argument(text: str, pos: int) -> int | None:
    k = _skip_spaces(text, pos)
    _, end = _read_braced(text, k)
    if end == k:
        return None
    return end


def _render_raisebox(text: str, pos: int) -> tuple[str | None, int]:
    k = _skip_spaces(text, pos)
    _, after_dim = _read_braced(text, k)
    if after_dim == k:
        return None, pos
    after_square_args = _consume_square_args(text, after_dim, max_count=2)
    if after_square_args is None:
        return None, pos
    k = after_square_args
    inner, end = _read_braced(text, k)
    if inner is None:
        return None, pos
    rendered = _math_to_text(inner)
    if rendered is None:
        return None, pos
    return rendered, end


def _render_accent_command(
    text: str,
    pos: int,
    name: str,
) -> tuple[str | None, int]:
    inner, end = _read_math_argument(text, pos)
    if inner is None:
        return None, pos
    rendered = _math_to_text(inner)
    if rendered is None:
        return None, pos
    return _apply_combining_mark(rendered, _MATH_ACCENT_COMMANDS[name]), end


def _read_math_argument(text: str, pos: int) -> tuple[str | None, int]:
    k = _skip_spaces(text, pos)
    if k >= len(text):
        return None, pos
    if text[k] == "{":
        return _read_braced(text, k)
    if text[k] == "\\":
        j = k + 1
        while j < len(text) and (text[j].isalpha() or text[j] == "@"):
            j += 1
        if j == k + 1:
            if j < len(text):
                return text[k : j + 1], j + 1
            return None, pos
        return text[k:j], j
    return text[k], k + 1


def _apply_combining_mark(text: str, mark: str) -> str:
    rendered: list[str] = []
    for ch in text:
        rendered.append(ch)
        if not ch.isspace():
            rendered.append(mark)
    return "".join(rendered)


def _render_math_environment(text: str, pos: int) -> tuple[str | None, int]:
    k = _skip_spaces(text, pos)
    env_name, after_name = _read_braced(text, k)
    if env_name is None or env_name not in _MATH_TEXT_ENVS:
        return None, pos

    body_start = after_name
    if env_name in {"array", "tabular"}:
        arg_start = _skip_spaces(text, body_start)
        if arg_start < len(text) and text[arg_start] == "{":
            _, after_colspec = _read_braced(text, arg_start)
            if after_colspec == arg_start:
                return None, pos
            body_start = after_colspec

    env_body, end = _read_environment_body(text, body_start)
    if env_body is None:
        return None, pos

    row_separator = "; " if env_name in _MATH_TEXT_CASE_ENVS else " / "
    rendered = _render_math_rows(
        env_body,
        row_separator=row_separator,
        cases=env_name in _MATH_TEXT_CASE_ENVS,
    )
    if rendered is None:
        return None, pos

    delimiters = _MATH_TEXT_ENV_DELIMITERS.get(env_name)
    if delimiters is not None:
        left, right = delimiters
        rendered = f"{left}{rendered}{right}"
    return rendered, end


def _read_environment_body(text: str, pos: int) -> tuple[str | None, int]:
    depth = 1
    i = pos
    n = len(text)
    while i < n:
        if text[i] != "\\":
            i += 1
            continue
        j = i + 1
        while j < n and (text[j].isalpha() or text[j] == "@"):
            j += 1
        name = text[i + 1 : j]
        if name not in {"begin", "end"}:
            i = j if j > i + 1 else i + 1
            continue
        k = _skip_spaces(text, j)
        env_name, after_env = _read_braced(text, k)
        if env_name is None:
            i = j
            continue
        if name == "begin":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return text[pos:i], after_env
        i = after_env
    return None, pos


def _render_math_rows(
    body: str,
    *,
    row_separator: str,
    cases: bool = False,
) -> str | None:
    rendered_rows: list[str] = []
    for row in _split_math_rows(body):
        if not row.strip():
            continue
        cells = _split_math_cells(row)
        rendered_cells: list[str] = []
        for cell in cells:
            rendered_cell = _math_to_text(cell.strip())
            if rendered_cell is None:
                return None
            rendered_cell = rendered_cell.strip()
            if rendered_cell:
                rendered_cells.append(rendered_cell)
        if not rendered_cells:
            continue
        if cases and len(rendered_cells) > 1:
            row_text = f"{rendered_cells[0]} | {' '.join(rendered_cells[1:])}"
        else:
            row_text = " ".join(rendered_cells)
        rendered_rows.append(row_text)
    return row_separator.join(rendered_rows)


def _split_math_rows(body: str) -> list[str]:
    rows: list[str] = []
    start = 0
    i = 0
    n = len(body)
    brace_depth = 0
    env_depth = 0
    while i < n:
        ch = body[i]
        if ch == "\\":
            if (
                i + 1 < n
                and body[i + 1] == "\\"
                and brace_depth == 0
                and env_depth == 0
            ):
                rows.append(body[start:i].strip())
                i = _consume_optional_square_arg(body, i + 2)
                start = i
                continue
            env_delta, after_env = _environment_depth_delta(body, i)
            if env_delta != 0:
                env_depth = max(0, env_depth + env_delta)
                i = after_env
                continue
            if i + 1 < n and body[i + 1] in "{}%#&":
                i += 2
                continue
            i += 1
            continue
        if ch == "{":
            brace_depth += 1
        elif ch == "}" and brace_depth > 0:
            brace_depth -= 1
        i += 1
    rows.append(body[start:].strip())
    return rows


def _split_math_cells(row: str) -> list[str]:
    cells: list[str] = []
    start = 0
    i = 0
    n = len(row)
    brace_depth = 0
    env_depth = 0
    while i < n:
        ch = row[i]
        if ch == "\\":
            env_delta, after_env = _environment_depth_delta(row, i)
            if env_delta != 0:
                env_depth = max(0, env_depth + env_delta)
                i = after_env
                continue
            if i + 1 < n and row[i + 1] in "{}%#&":
                i += 2
                continue
            i += 1
            continue
        if ch == "{":
            brace_depth += 1
        elif ch == "}" and brace_depth > 0:
            brace_depth -= 1
        elif ch == "&" and brace_depth == 0 and env_depth == 0:
            cells.append(row[start:i].strip())
            start = i + 1
        i += 1
    cells.append(row[start:].strip())
    return cells


def _environment_depth_delta(text: str, pos: int) -> tuple[int, int]:
    n = len(text)
    j = pos + 1
    while j < n and (text[j].isalpha() or text[j] == "@"):
        j += 1
    name = text[pos + 1 : j]
    if name not in {"begin", "end"}:
        return 0, pos
    k = _skip_spaces(text, j)
    env_name, after_env = _read_braced(text, k)
    if env_name is None:
        return 0, pos
    return (1 if name == "begin" else -1), after_env


def _consume_square_args(text: str, pos: int, *, max_count: int) -> int | None:
    k = pos
    for _ in range(max_count):
        start = _skip_spaces(text, k)
        if start >= len(text) or text[start] != "[":
            return start
        end = _consume_optional_square_arg(text, start)
        if end <= start:
            return None
        k = end
    return _skip_spaces(text, k)


def _consume_optional_square_arg(text: str, pos: int) -> int:
    k = _skip_spaces(text, pos)
    if k >= len(text) or text[k] != "[":
        return k
    i = k + 1
    escaped = False
    while i < len(text):
        ch = text[i]
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "]":
            return i + 1
        i += 1
    return pos


def _skip_spaces(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in " \t\n\r":
        pos += 1
    return pos


def _read_braced(text: str, pos: int) -> tuple[str | None, int]:
    if pos >= len(text) or text[pos] != "{":
        return None, pos
    depth = 0
    i = pos
    escaped = False
    while i < len(text):
        c = text[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if c == "\\":
            escaped = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[pos + 1 : i], i + 1
        i += 1
    return None, pos


def _consume_script(
    body: str,
    pos: int,
    table: dict[str, str],
    out: list[str],
    *,
    html_tag: str,
) -> int | None:
    n = len(body)
    if pos >= n:
        return None
    if body[pos] == "{":
        inner, end = _read_braced(body, pos)
        if inner is None or not inner:
            return None

        rendered: list[str] = []
        unicode_ok = True
        for ch in inner:
            if ch == " ":
                continue
            mapped = table.get(ch)
            if mapped is None:
                unicode_ok = False
                break
            rendered.append(mapped)
        if unicode_ok:
            out.append("".join(rendered))
            return end

        text_render = _math_to_text(inner)
        if text_render is None:
            return None
        text_render = text_render.strip()
        if not text_render:
            return end
        out.append(f"<{html_tag}>{text_render}</{html_tag}>")
        return end
    if body[pos] == "\\":
        raw_arg, end = _read_script_command_argument(body, pos)
        if raw_arg is None:
            return None
        text_render = _math_to_text(raw_arg)
        if text_render is None:
            return None
        text_render = text_render.strip()
        if not text_render:
            return end
        out.append(f"<{html_tag}>{text_render}</{html_tag}>")
        return end
    ch = body[pos]
    mapped = table.get(ch)
    if mapped is not None:
        out.append(mapped)
        return pos + 1

    if ch.isalnum():
        out.append(f"<{html_tag}>{ch}</{html_tag}>")
        return pos + 1
    return None


def _has_backslash_at(body: str, pos: int) -> bool:
    return pos < len(body) and body[pos] == "\\"


def _consume_braced_span(body: str, pos: int) -> int | None:
    k = _skip_spaces(body, pos)
    _, end = _read_braced(body, k)
    if end == k:
        return None
    return end


def _consume_layout_span(body: str, pos: int, name: str) -> int | None:
    k = _skip_spaces(body, pos)
    if name == "smash":
        after_square_args = _consume_square_args(body, k, max_count=1)
        if after_square_args is None:
            return None
        k = after_square_args
    return _consume_braced_span(body, k)


def _consume_raisebox_span(body: str, pos: int) -> int | None:
    _, end = _render_raisebox(body, pos)
    if end == pos:
        return None
    return end


def _consume_accent_span(body: str, pos: int) -> int | None:
    _, end = _read_math_argument(body, pos)
    if end == pos:
        return None
    return end


def _consume_command_span(body: str, pos_after_name: int, name: str) -> int | None:
    if name in _MATH_UNICODE:
        return pos_after_name
    if name in _MATH_TEXT_DECLARATIONS:
        return None
    if name in _MATH_TEXT_WRAPPERS:
        return _consume_braced_span(body, pos_after_name)
    if name in _MATH_LAYOUT_WRAPPERS:
        return _consume_layout_span(body, pos_after_name, name)
    if name in _MATH_PHANTOM_COMMANDS:
        return _consume_discarded_braced_argument(body, pos_after_name)
    if name == "raisebox":
        return _consume_raisebox_span(body, pos_after_name)
    if name in _MATH_ACCENT_COMMANDS:
        return _consume_accent_span(body, pos_after_name)
    return pos_after_name


def _read_script_command_argument(body: str, pos: int) -> tuple[str | None, int]:
    if not _has_backslash_at(body, pos):
        return None, pos
    name, end_name = _read_command_name(body, pos + 1, len(body))
    if name is None:
        return None, pos
    end = _consume_command_span(body, end_name, name)
    if end is None:
        return None, pos
    return body[pos:end], end


# ---------------------------------------------------------------------------
# Exported set of all command names that are valid in math mode.
# Used by the inline engine to suppress unknown-command counting for
# commands that are legitimate math-mode TeX but have no text-mode handler.
# ---------------------------------------------------------------------------

_MATH_OPERATORS: frozenset[str] = frozenset(
    {
        "arccos",
        "arcsin",
        "arctan",
        "arg",
        "cos",
        "cosh",
        "cot",
        "coth",
        "csc",
        "deg",
        "det",
        "dim",
        "exp",
        "gcd",
        "hom",
        "inf",
        "ker",
        "lg",
        "lim",
        "liminf",
        "limsup",
        "ln",
        "log",
        "max",
        "min",
        "Pr",
        "sec",
        "sin",
        "sinh",
        "sup",
        "tan",
        "tanh",
    }
)

_MATH_EXTRA: frozenset[str] = frozenset(
    {
        # Delimiter sizing
        "big",
        "Big",
        "bigg",
        "Bigg",
        "bigl",
        "Bigl",
        "biggl",
        "Biggl",
        "bigr",
        "Bigr",
        "biggr",
        "Biggr",
        "bigm",
        "Bigm",
        "biggm",
        "Biggm",
        # Over/under constructs
        "underbrace",
        "overbrace",
        "underset",
        "overset",
        "stackrel",
        "substack",
        # Spacing
        "mkern",
        "mskip",
        "kern",
        "hskip",
        "quad",
        "qquad",
        "thinspace",
        "thickspace",
        "negthinspace",
        "negmedspace",
        "negthickspace",
        # Atom classification
        "mathrel",
        "mathop",
        "mathbin",
        "mathord",
        "mathopen",
        "mathclose",
        "mathpunct",
        "mathinner",
        # Relations / symbols not in _MATH_UNICODE
        "mid",
        "nmid",
        "parallel",
        "nparallel",
        "not",
        # Operator variants
        "operatornamewithlimits",
        # Misc
        "cal",
        "mit",
        "bmod",
        "pmod",
        "pod",
        "mod",
        # Stretchy delimiters handled by \left/\right
        "lbrace",
        "rbrace",
        "lvert",
        "rvert",
        "lVert",
        "rVert",
        "backslash",
        # Color in math
        "color",
        "textcolor",
    }
)

KNOWN_MATH_COMMANDS: frozenset[str] = (
    frozenset(_MATH_UNICODE.keys())
    | _MATH_TEXT_DECLARATIONS
    | _MATH_TEXT_WRAPPERS
    | frozenset(_MATH_ACCENT_COMMANDS.keys())
    | _MATH_LAYOUT_WRAPPERS
    | _MATH_PHANTOM_COMMANDS
    | _MATH_TEXT_LOSSY_WRAPPERS
    | _MATH_OPERATORS
    | _MATH_EXTRA
)


# TeX commands unsupported by KaTeX → compatible equivalents
_KATEX_COMPAT: dict[str, str] = {
    "mbox": "text",
    "hbox": "text",
}
_KATEX_COMPAT_RE = re.compile(
    r"\\(" + "|".join(re.escape(k) for k in _KATEX_COMPAT) + r")(?![A-Za-z@])"
)


def katex_normalize(body: str) -> str:
    """Replace TeX primitives that KaTeX doesn't recognize."""
    return _KATEX_COMPAT_RE.sub(
        lambda m: "\\" + _KATEX_COMPAT[m.group(1)], body
    )
