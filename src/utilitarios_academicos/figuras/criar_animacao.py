"""Gera uma animação (GIF ou MP4) com as figuras de uma pasta.

Os quadros são tomados em ordem natural de nome, centralizados em uma tela
do tamanho do maior quadro, sobre fundo branco. Opcionalmente, descarta o
primeiro quadro (por exemplo, o instante inicial do modelo) e toma um
quadro a cada `passo`.

Uso:
    criar-animacao PASTA [--saida 01_animacao.gif] [--duracao-ms 1200]
                         [--passo 1] [--pular-primeiro] [--largura PX]

O formato é definido pela extensão da saída: .gif (Pillow) ou .mp4
(imageio-ffmpeg; instalar com o extra "video").

Consolida criar_animacao.ipynb, criar_animacao.ipynb (TCC),
01_v1_ANIMACOES.ipynb (ARTIGO_TCC) e 02_animacoes_defesa.py (TCC).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from utilitarios_academicos.figuras._quadros import abrir_rgb, centralizar, listar_figuras


def selecionar_quadros(caminhos: list[Path], passo: int = 1, pular_primeiro: bool = False) -> list[Path]:
    """Descarta o primeiro quadro, se pedido, e toma um a cada `passo`."""
    if passo < 1:
        raise ValueError("passo deve ser positivo")
    caminhos = caminhos[1:] if pular_primeiro else list(caminhos)
    return caminhos[::passo]


def criar_animacao(pasta: Path, saida: Path | str = "01_animacao.gif", formato: str = "png",
                   duracao_ms: int = 1200, loop: int = 0, passo: int = 1,
                   pular_primeiro: bool = False, largura: int | None = None) -> Path:
    """Gera a animação e devolve o caminho do arquivo salvo (relativo a `pasta` se não absoluto)."""
    saida = Path(saida)
    saida = saida if saida.is_absolute() else pasta / saida
    caminhos = selecionar_quadros(listar_figuras(pasta, formato, excluir=saida), passo, pular_primeiro)
    if not caminhos:
        raise RuntimeError("Nenhum quadro restou após a seleção.")

    figuras = [abrir_rgb(p, largura) for p in caminhos]
    tela_l = max(f.width for f in figuras)
    tela_a = max(f.height for f in figuras)
    extensao = saida.suffix.casefold()

    if extensao == ".gif":
        from PIL import Image

        quadros = [centralizar(f, tela_l, tela_a).convert("P", palette=Image.ADAPTIVE) for f in figuras]
        quadros[0].save(saida, save_all=True, append_images=quadros[1:],
                        duration=duracao_ms, loop=loop, disposal=2)
    elif extensao == ".mp4":
        try:
            import imageio.v2 as imageio
            import numpy as np
        except ImportError as erro:
            raise RuntimeError("MP4 requer o extra 'video' (imageio, imageio-ffmpeg, numpy).") from erro
        # libx264 exige dimensões pares
        tela_l += tela_l % 2
        tela_a += tela_a % 2
        fps = 1000.0 / duracao_ms
        with imageio.get_writer(saida, fps=fps, codec="libx264", quality=8, macro_block_size=1) as escritor:
            for figura in figuras:
                escritor.append_data(np.asarray(centralizar(figura, tela_l, tela_a)))
    else:
        raise ValueError(f"Extensão de saída não suportada: {saida.suffix} (use .gif ou .mp4)")
    return saida


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="criar-animacao", description=__doc__.splitlines()[0])
    parser.add_argument("pasta", type=Path)
    parser.add_argument("--saida", default="01_animacao.gif", help=".gif ou .mp4 (relativo à pasta)")
    parser.add_argument("--formato", default="png", help="extensão dos quadros de entrada")
    parser.add_argument("--duracao-ms", type=int, default=1200, help="duração de cada quadro, em ms")
    parser.add_argument("--loop", type=int, default=0, help="repetições do GIF (0 = infinito)")
    parser.add_argument("--passo", type=int, default=1, help="usa um quadro a cada PASSO")
    parser.add_argument("--pular-primeiro", action="store_true", help="descarta o primeiro quadro")
    parser.add_argument("--largura", type=int, help="largura final dos quadros, em pixels")
    args = parser.parse_args(argv)
    try:
        saida = criar_animacao(args.pasta, args.saida, args.formato, args.duracao_ms, args.loop,
                               args.passo, args.pular_primeiro, args.largura)
    except Exception as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    print(f"Animação gerada: {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
