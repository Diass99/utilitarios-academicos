"""Leitura e padronização de quadros (figuras) para mosaicos e animações."""

from __future__ import annotations

from pathlib import Path

from utilitarios_academicos.ordenacao import chave_natural


def listar_figuras(pasta: Path, formato: str = "png", excluir: Path | None = None) -> list[Path]:
    """Figuras de `pasta` com a extensão `formato`, em ordem natural."""
    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")
    excluir = excluir.resolve() if excluir else None
    caminhos = [p for p in pasta.glob(f"*.{formato.lstrip('.')}") if p.resolve() != excluir]
    if not caminhos:
        raise RuntimeError(f"Nenhum arquivo .{formato.lstrip('.')} encontrado em {pasta}")
    return sorted(caminhos, key=lambda p: chave_natural(p.name))


def abrir_rgb(caminho: Path, largura: int | None = None):
    """Abre a figura em RGB sobre fundo branco; redimensiona para `largura`, se informada."""
    from PIL import Image

    with Image.open(caminho) as original:
        imagem = original.convert("RGBA")
    fundo = Image.new("RGBA", imagem.size, (255, 255, 255, 255))
    imagem = Image.alpha_composite(fundo, imagem).convert("RGB")
    if largura and imagem.width != largura:
        altura = round(imagem.height * largura / imagem.width)
        imagem = imagem.resize((largura, altura), Image.LANCZOS)
    return imagem


def centralizar(imagem, largura: int, altura: int, cor=(255, 255, 255)):
    """Centraliza `imagem` em uma tela branca de largura × altura."""
    from PIL import Image

    tela = Image.new("RGB", (largura, altura), cor)
    tela.paste(imagem, ((largura - imagem.width) // 2, (altura - imagem.height) // 2))
    return tela
