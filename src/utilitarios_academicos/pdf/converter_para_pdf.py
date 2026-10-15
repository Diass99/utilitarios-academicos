"""Converte arquivos de texto, código, Office e imagens para PDF.

Cada arquivo gera um PDF homônimo no mesmo diretório. Uma pasta é
percorrida recursivamente; arquivos PDF são ignorados.

Uso:
    converter-para-pdf ARQUIVO_OU_PASTA

Derivado de conversor_para_pdf_universal.py.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

EXTENSOES_IMAGEM = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
EXTENSOES_LIBREOFFICE = {
    ".txt", ".csv", ".py", ".sh", ".js", ".json", ".html", ".md",
    ".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods",
    ".ppt", ".pptx", ".odp", ".ipynb", ".f90", ".c", ".cpp", ".h",
    ".log", ".conf", ".ini",
}


def localizar_libreoffice() -> str:
    caminho = shutil.which("libreoffice") or shutil.which("soffice")
    if not caminho:
        raise RuntimeError("LibreOffice não encontrado (sudo apt install libreoffice).")
    return caminho


def converter_libreoffice(origem: Path, executavel: str) -> Path:
    comando = [executavel, "--headless", "--convert-to", "pdf", "--outdir", str(origem.parent), str(origem)]
    resultado = subprocess.run(comando, capture_output=True, text=True, check=False)
    if resultado.returncode != 0:
        raise RuntimeError(f"Falha na conversão pelo LibreOffice: {resultado.stderr.strip()}")
    return origem.with_suffix(".pdf")


def converter_imagem(origem: Path) -> Path:
    """Gera um PDF de página única com as dimensões da imagem."""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    from PIL import Image, ImageOps

    destino = origem.with_suffix(".pdf")
    temporaria = origem.with_name(f".{origem.stem}.tmp.png")
    with Image.open(origem) as original:
        imagem = ImageOps.exif_transpose(original)
        if imagem.mode not in {"RGB", "RGBA", "L"}:
            imagem = imagem.convert("RGBA" if "A" in imagem.getbands() else "RGB")
        largura, altura = imagem.size
        imagem.save(temporaria, format="PNG")
    documento = fitz.open()
    try:
        pagina = documento.new_page(width=largura, height=altura)
        pagina.insert_image(fitz.Rect(0, 0, largura, altura), filename=str(temporaria))
        documento.save(destino)
    finally:
        documento.close()
        temporaria.unlink(missing_ok=True)
    return destino


def converter(alvo: Path, libreoffice: str | None = None) -> list[Path]:
    """Converte um arquivo ou todos os arquivos de uma pasta; devolve os PDFs gerados."""
    if alvo.is_file():
        arquivos = [alvo]
    elif alvo.is_dir():
        arquivos = sorted(p for p in alvo.rglob("*") if p.is_file())
    else:
        raise FileNotFoundError(f"Caminho inválido: {alvo}")

    gerados = []
    for arquivo in arquivos:
        extensao = arquivo.suffix.casefold()
        if extensao == ".pdf":
            continue
        print(f"Processando: {arquivo.name}...", end=" ", flush=True)
        try:
            if extensao in EXTENSOES_IMAGEM:
                gerados.append(converter_imagem(arquivo))
                print("OK (imagem)")
                continue
            if extensao not in EXTENSOES_LIBREOFFICE:
                arquivo.read_text(encoding="utf-8")  # extensão não mapeada: tenta como texto
            libreoffice = libreoffice or localizar_libreoffice()
            gerados.append(converter_libreoffice(arquivo, libreoffice))
            print("OK (LibreOffice)")
        except UnicodeDecodeError:
            print("IGNORADO (formato binário não suportado)")
        except Exception as erro:
            print(f"ERRO: {erro}")
    return gerados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="converter-para-pdf", description=__doc__.splitlines()[0])
    parser.add_argument("alvo", type=Path, help="arquivo ou pasta")
    args = parser.parse_args(argv)
    try:
        gerados = converter(args.alvo.resolve())
    except Exception as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    print(f"\nConcluído: {len(gerados)} PDF(s) gerado(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
