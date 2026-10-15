"""Testes dos utilitários (sem rede e sem LibreOffice)."""

from pathlib import Path

import pytest
from PIL import Image

from utilitarios_academicos.figuras.criar_animacao import criar_animacao, selecionar_quadros
from utilitarios_academicos.figuras.criar_mosaico import criar_mosaico
from utilitarios_academicos.ordenacao import chave_natural, chave_por_data
from utilitarios_academicos.referencias.organizar_referencias import (
    _destacado, nome_padrao, tem_autor_destacado,
)


def _figuras(pasta: Path, tamanhos):
    for i, (largura, altura) in enumerate(tamanhos, start=1):
        Image.new("RGB", (largura, altura), (10 * i, 0, 0)).save(pasta / f"quadro_{i}.png")


# Ordenação ----------------------------------------------------------
def test_ordem_natural():
    nomes = ["f10.png", "f2.png", "F1.png", "é3.png"]
    assert sorted(nomes, key=chave_natural) == ["é3.png", "F1.png", "f2.png", "f10.png"]


def test_ordem_por_data():
    nomes = ["b_02-01-2026.pdf", "a_15-12-2025.pdf", "sem_data.pdf"]
    assert sorted(nomes, key=chave_por_data) == ["sem_data.pdf", "a_15-12-2025.pdf", "b_02-01-2026.pdf"]


# Figuras ------------------------------------------------------------
def test_mosaico_dimensoes(tmp_path):
    _figuras(tmp_path, [(40, 30), (20, 50), (30, 30)])
    saida = criar_mosaico(tmp_path, colunas=2, linhas=2)
    with Image.open(saida) as mosaico:
        assert mosaico.size == (80, 100)
        assert mosaico.getpixel((79, 99)) == (255, 255, 255)  # célula vazia em branco


def test_mosaico_ignora_saida_anterior(tmp_path):
    _figuras(tmp_path, [(10, 10)])
    criar_mosaico(tmp_path, colunas=1, linhas=1)
    with Image.open(criar_mosaico(tmp_path, colunas=2, linhas=1)) as mosaico:
        assert mosaico.size == (20, 10)


def test_selecao_de_quadros():
    quadros = [Path(f"q{i}.png") for i in range(7)]
    assert selecionar_quadros(quadros, passo=6, pular_primeiro=True) == [Path("q1.png")]
    assert selecionar_quadros(quadros, passo=2) == [Path(f"q{i}.png") for i in (0, 2, 4, 6)]
    with pytest.raises(ValueError):
        selecionar_quadros(quadros, passo=0)


def test_animacao_gif(tmp_path):
    _figuras(tmp_path, [(30, 20), (30, 20), (20, 30)])
    saida = criar_animacao(tmp_path, "anim.gif", duracao_ms=500, pular_primeiro=True)
    with Image.open(saida) as gif:
        assert gif.n_frames == 2
        assert gif.size == (30, 30)


# Referências --------------------------------------------------------
REGISTRO = {
    "author": [{"family": "Rodrigues", "given": "Regina R."}, {"family": "Dias", "given": "Vinícius"}],
    "title": ["Marine heatwaves &amp; <i>coastal</i> rainfall: a test"],
    "issued": {"date-parts": [[2026, 3]]},
}


def test_nome_padrao_com_destaque():
    destacado = _destacado("rodrigues,regina,REGINA")
    assert tem_autor_destacado(REGISTRO, destacado)
    assert nome_padrao(REGISTRO, destacado=destacado) == "REGINA_RODRIGUES_2026_Marine_heatwaves_coastal_rainfall_a_test.pdf"


def test_nome_padrao_preprint_sem_destaque():
    assert nome_padrao(REGISTRO, preprint=True).endswith("_PREPRINT.pdf")
    assert not nome_padrao(REGISTRO).startswith("REGINA_")


# PDF ----------------------------------------------------------------
def test_juntar_pdf_e_imagem(tmp_path):
    import pymupdf

    from utilitarios_academicos.pdf.juntar_documentos import compilar

    documento = pymupdf.open()
    documento.new_page()
    documento.save(tmp_path / "02_artigo.pdf")
    documento.close()
    Image.new("RGB", (60, 30), (0, 0, 0)).save(tmp_path / "01_figura.png")

    saida = compilar(tmp_path, tmp_path / "acervo.pdf")
    with pymupdf.open(saida) as acervo:
        assert acervo.page_count == 4  # duas capas, uma figura e uma página de PDF
        assert [item[1] for item in acervo.get_toc()] == ["01_figura.png", "02_artigo.pdf"]
