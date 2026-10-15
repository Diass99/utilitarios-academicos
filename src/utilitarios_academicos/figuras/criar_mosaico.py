"""Monta um mosaico (grade de linhas × colunas) com as figuras de uma pasta.

As figuras são tomadas em ordem natural de nome, até preencher a grade, e
centralizadas em células de tamanho igual ao da maior figura, sobre fundo
branco.

Uso:
    criar-mosaico PASTA [--colunas 2] [--linhas 2] [--formato png] [--saida 01_mosaico.png]

Derivado de criar_mosaico.ipynb. Diferença em relação ao original: as
figuras são centralizadas sobre fundo branco (antes, alinhadas ao canto
superior esquerdo sobre fundo preto).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from utilitarios_academicos.figuras._quadros import abrir_rgb, centralizar, listar_figuras


def criar_mosaico(pasta: Path, colunas: int = 2, linhas: int = 2, formato: str = "png",
                  saida: Path | str = "01_mosaico.png") -> Path:
    """Gera o mosaico e devolve o caminho do arquivo salvo (relativo a `pasta` se não absoluto)."""
    from PIL import Image

    if colunas < 1 or linhas < 1:
        raise ValueError("colunas e linhas devem ser positivos")
    saida = Path(saida)
    saida = saida if saida.is_absolute() else pasta / saida
    caminhos = listar_figuras(pasta, formato, excluir=saida)[: colunas * linhas]
    figuras = [abrir_rgb(p) for p in caminhos]
    largura = max(f.width for f in figuras)
    altura = max(f.height for f in figuras)

    mosaico = Image.new("RGB", (colunas * largura, linhas * altura), (255, 255, 255))
    for indice, figura in enumerate(figuras):
        linha, coluna = divmod(indice, colunas)
        mosaico.paste(centralizar(figura, largura, altura), (coluna * largura, linha * altura))
    mosaico.save(saida)
    return saida


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="criar-mosaico", description=__doc__.splitlines()[0])
    parser.add_argument("pasta", type=Path)
    parser.add_argument("--colunas", type=int, default=2)
    parser.add_argument("--linhas", type=int, default=2)
    parser.add_argument("--formato", default="png", help="extensão das figuras de entrada")
    parser.add_argument("--saida", default="01_mosaico.png", help="arquivo de saída (relativo à pasta)")
    args = parser.parse_args(argv)
    try:
        saida = criar_mosaico(args.pasta, args.colunas, args.linhas, args.formato, args.saida)
    except Exception as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    print(f"Mosaico gerado: {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
