"""Todo arquivo .js do painel precisa ao menos compilar: um erro de sintaxe derruba a página inteira em silêncio
(aconteceu em 19/10: a tela Dashboards parou de abrir e os testes em Python não perceberam)."""

import shutil
import subprocess
from pathlib import Path

import pytest

ESTATICOS = Path(__file__).resolve().parents[1] / "robo" / "painel" / "estaticos"


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js não instalado neste computador")
@pytest.mark.parametrize("arquivo", sorted(p.name for p in ESTATICOS.glob("*.js")))
def teste_js_compila(arquivo):
    r = subprocess.run(["node", "--check", str(ESTATICOS / arquivo)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
