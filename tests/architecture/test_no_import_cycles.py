from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest


@pytest.mark.architecture
def test_public_import_is_clean() -> None:
    script = textwrap.dedent(
        """
        import sys
        import arxiv_md  # noqa: F401
        leaked = sorted(
            m for m in sys.modules
            if m.startswith(("hypothesis", "pytest", "tests", "pypdfium2", "PIL"))
        )
        assert not leaked, leaked
        print("OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("OK")
