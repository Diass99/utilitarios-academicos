"""Compila em um único PDF os documentos, imagens e códigos de uma pasta.

Cada arquivo é precedido por uma página de capa com sua categoria e seu nome,
e o PDF final recebe um sumário (marcadores) com o caminho relativo de cada
arquivo. Arquivos Office e de código são convertidos pelo LibreOffice.

Uso:
    juntar-documentos [PASTA] [--ordem natural|data] [--saida ARQUIVO.pdf]

Derivado de juntar_documentos_V5.py e juntar_documentos_por_data.py.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from utilitarios_academicos.ordenacao import chave_natural, chave_por_data

EXTENSOES_PDF = {".pdf"}
EXTENSOES_IMAGEM = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
EXTENSOES_OFFICE = {
    ".doc", ".docx", ".odt", ".rtf", ".csv",
    ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp",
}
EXTENSOES_CODIGO = {
    ".tex", ".bib", ".py", ".ipynb", ".sh", ".r", ".f90",
    ".c", ".cpp", ".h", ".m", ".txt", ".json",
}
EXTENSOES_SUPORTADAS = EXTENSOES_PDF | EXTENSOES_IMAGEM | EXTENSOES_OFFICE | EXTENSOES_CODIGO

# Compilações anteriores não são reincorporadas
PADRAO_COMPILACAO_ANTERIOR = re.compile(r"^documentos_juntos\d+(?:_compressed)?\.pdf$", re.IGNORECASE)

MARGEM_PT = 18.0
A4_LARGURA_PT, A4_ALTURA_PT = 595.0, 842.0

ORDENS = {"natural": chave_natural, "data": chave_por_data}


def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:  # versões anteriores a 1.24
        import fitz
    return fitz


def nome_saida_padrao(raiz: Path) -> str:
    """Nome do PDF derivado do caminho absoluto da pasta ('/' substituída por '-')."""
    nome = str(raiz.resolve()).replace("/", "-").strip("-")
    return f"{nome or 'ACERVO_DOCUMENTOS'}.pdf"


def _parte_oculta(partes) -> bool:
    return any(parte.startswith(".") for parte in partes)


def localizar_documentos(raiz: Path, ordem: str = "natural",
                         ignorar: set[Path] | None = None) -> tuple[list[Path], list[Path]]:
    """Separa os arquivos da pasta em suportados e não suportados, já ordenados."""
    ignorar = {p.resolve() for p in (ignorar or set())}
    chave = ORDENS[ordem]
    documentos: list[Path] = []
    nao_suportados: list[Path] = []
    for caminho in raiz.rglob("*"):
        if not caminho.is_file() or caminho.is_symlink():
            continue
        relativo = caminho.relative_to(raiz)
        if caminho.resolve() in ignorar or _parte_oculta(relativo.parts):
            continue
        if caminho.parent == raiz and PADRAO_COMPILACAO_ANTERIOR.match(caminho.name):
            continue
        if caminho.suffix.casefold() in EXTENSOES_SUPORTADAS:
            documentos.append(caminho)
        else:
            nao_suportados.append(caminho)
    documentos.sort(key=lambda p: chave(p.relative_to(raiz)))
    nao_suportados.sort(key=lambda p: chave(p.relative_to(raiz)))
    return documentos, nao_suportados


def localizar_libreoffice() -> str | None:
    return shutil.which("libreoffice") or shutil.which("soffice")


def converter_office_para_pdf(origem: Path, pasta_trabalho: Path, libreoffice: str, indice: int) -> Path:
    pasta_saida = pasta_trabalho / f"office_{indice:04d}"
    perfil = pasta_trabalho / f"perfil_lo_{indice:04d}"
    pasta_saida.mkdir(parents=True, exist_ok=True)
    perfil.mkdir(parents=True, exist_ok=True)
    comando = [
        libreoffice, "--headless",
        f"-env:UserInstallation={perfil.resolve().as_uri()}",
        "--convert-to", "pdf", "--outdir", str(pasta_saida), str(origem),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True, check=False)
    candidatos = sorted(pasta_saida.glob("*.pdf"), key=chave_natural)
    if resultado.returncode != 0 or not candidatos:
        detalhes = (resultado.stderr or resultado.stdout).strip()
        raise RuntimeError(f"Falha ao converter com o LibreOffice: {origem.name}"
                           + (f"\n{detalhes}" if detalhes else ""))
    return candidatos[0]


def adicionar_capa(destino, categoria: str, nome_arquivo: str) -> int:
    fitz = _fitz()
    pagina = destino.new_page(width=A4_LARGURA_PT, height=A4_ALTURA_PT)
    retangulo = fitz.Rect(50, A4_ALTURA_PT / 2 - 100, A4_LARGURA_PT - 50, A4_ALTURA_PT / 2 + 100)
    pagina.insert_textbox(retangulo, f"{categoria}:\n\n{nome_arquivo}", fontsize=20, fontname="helv", align=1)
    return 1


def anexar_pdf(destino, origem: Path) -> int:
    fitz = _fitz()
    with fitz.open(origem) as documento:
        if documento.needs_pass:
            raise RuntimeError(f"PDF protegido por senha: {origem.name}")
        if documento.page_count == 0:
            raise RuntimeError(f"PDF sem páginas: {origem.name}")
        destino.insert_pdf(documento)
        return documento.page_count


def _preparar_imagem(origem: Path, pasta_trabalho: Path, indice: int) -> tuple[Path, int, int]:
    from PIL import Image, ImageOps

    with Image.open(origem) as original:
        imagem = ImageOps.exif_transpose(original)
        largura, altura = imagem.size
        if imagem.mode not in {"RGB", "RGBA", "L"}:
            imagem = imagem.convert("RGBA" if "A" in imagem.getbands() else "RGB")
        if imagem.mode == "RGB" and origem.suffix.casefold() in {".jpg", ".jpeg"}:
            destino = pasta_trabalho / f"imagem_{indice:04d}.jpg"
            imagem.save(destino, format="JPEG", quality=95, optimize=True)
        else:
            destino = pasta_trabalho / f"imagem_{indice:04d}.png"
            imagem.save(destino, format="PNG", optimize=True)
    return destino, largura, altura


def anexar_imagem(destino, origem: Path, pasta_trabalho: Path, indice: int) -> int:
    fitz = _fitz()
    imagem, largura_px, altura_px = _preparar_imagem(origem, pasta_trabalho, indice)
    if altura_px >= largura_px:
        largura_pag, altura_pag = A4_LARGURA_PT, A4_ALTURA_PT
    else:
        largura_pag, altura_pag = A4_ALTURA_PT, A4_LARGURA_PT
    pagina = destino.new_page(width=largura_pag, height=altura_pag)
    escala = min((largura_pag - 2 * MARGEM_PT) / largura_px, (altura_pag - 2 * MARGEM_PT) / altura_px)
    largura, altura = largura_px * escala, altura_px * escala
    x0, y0 = (largura_pag - largura) / 2, (altura_pag - altura) / 2
    pagina.insert_image(fitz.Rect(x0, y0, x0 + largura, y0 + altura), filename=str(imagem), keep_proportion=True)
    return 1


def texto_do_codigo(origem: Path) -> str:
    """Texto de um arquivo de código; notebooks são linearizados por célula."""
    if origem.suffix.casefold() == ".ipynb":
        try:
            dados = json.loads(origem.read_text(encoding="utf-8"))
            partes = []
            for i, celula in enumerate(dados.get("cells", []), start=1):
                fonte = celula.get("source", [])
                fonte = "".join(fonte) if isinstance(fonte, list) else fonte
                partes.append(f"# --- [CELULA {i}: {celula.get('cell_type', '').upper()}] ---\n{fonte}\n")
            return "\n".join(partes)
        except (ValueError, OSError):
            pass
    return origem.read_text(errors="replace")


def anexar_codigo(destino, origem: Path, pasta_trabalho: Path, libreoffice: str, indice: int) -> int:
    arquivo_txt = pasta_trabalho / f"codigo_{indice:04d}.txt"
    arquivo_txt.write_text(texto_do_codigo(origem), encoding="utf-8")
    return anexar_pdf(destino, converter_office_para_pdf(arquivo_txt, pasta_trabalho, libreoffice, indice))


def _categoria(extensao: str) -> str:
    if extensao in EXTENSOES_PDF:
        return "Arquivo PDF"
    if extensao in EXTENSOES_IMAGEM:
        return "Arquivo de Imagem"
    if extensao in EXTENSOES_CODIGO:
        return "Arquivo de Codigo"
    return "Arquivo Office"


def compilar(raiz: Path, saida: Path | None = None, ordem: str = "natural", autor: str = "") -> Path:
    """Compila os documentos de `raiz` em um único PDF e devolve o caminho gerado."""
    fitz = _fitz()
    raiz = raiz.resolve()
    saida = (saida or raiz / nome_saida_padrao(raiz)).resolve()
    temporaria = saida.with_name(f".{saida.stem}.tmp.pdf")

    documentos, nao_suportados = localizar_documentos(raiz, ordem, ignorar={saida, temporaria})
    if not documentos:
        raise RuntimeError("Nenhum documento suportado foi encontrado.")

    precisa_lo = any(p.suffix.casefold() in (EXTENSOES_OFFICE | EXTENSOES_CODIGO) for p in documentos)
    libreoffice = localizar_libreoffice() if precisa_lo else None
    if precisa_lo and libreoffice is None:
        raise RuntimeError("Há arquivos que exigem o LibreOffice, que não está instalado "
                           "(sudo apt install libreoffice).")

    print(f"Raiz: {raiz}\nDocumentos a incorporar: {len(documentos)}\n")
    final = fitz.open()
    marcadores: list[list[object]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="juntar_documentos_") as temporario:
            trabalho = Path(temporario)
            for indice, caminho in enumerate(documentos, start=1):
                relativo = caminho.relative_to(raiz)
                pagina_inicial = final.page_count + 1
                extensao = caminho.suffix.casefold()
                print(f"[{indice:02d}/{len(documentos):02d}] {relativo}")
                adicionar_capa(final, _categoria(extensao), caminho.name)
                if extensao in EXTENSOES_PDF:
                    anexar_pdf(final, caminho)
                elif extensao in EXTENSOES_IMAGEM:
                    anexar_imagem(final, caminho, trabalho, indice)
                elif extensao in EXTENSOES_CODIGO:
                    anexar_codigo(final, caminho, trabalho, libreoffice, indice)
                else:
                    anexar_pdf(final, converter_office_para_pdf(caminho, trabalho, libreoffice, indice))
                marcadores.append([1, relativo.as_posix(), pagina_inicial])
        final.set_metadata({"title": saida.stem, "author": autor,
                            "subject": f"Compilacao documental (ordem: {ordem})",
                            "creator": "utilitarios-academicos/juntar-documentos"})
        final.set_toc(marcadores)
        final.save(temporaria, garbage=4, deflate=True, clean=True)
    except Exception:
        temporaria.unlink(missing_ok=True)
        raise
    finally:
        final.close()
    temporaria.replace(saida)

    if nao_suportados:
        print("\nAVISO: arquivos não incorporados (formato não suportado):")
        for caminho in nao_suportados:
            print(f"  - {caminho.relative_to(raiz)}")
    return saida


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="juntar-documentos", description=__doc__.splitlines()[0])
    parser.add_argument("pasta", nargs="?", default=".", type=Path, help="pasta de origem (padrão: atual)")
    parser.add_argument("--ordem", choices=sorted(ORDENS), default="natural",
                        help="natural: pelo caminho; data: pela data _DD-MM-AAAA no nome")
    parser.add_argument("--saida", type=Path, help="PDF de saída (padrão: nome derivado do caminho)")
    parser.add_argument("--autor", default="", help="autor gravado nos metadados do PDF")
    args = parser.parse_args(argv)
    try:
        saida = compilar(args.pasta, args.saida, args.ordem, args.autor)
    except Exception as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    print(f"\nConcluído: {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
