"""Chaves de ordenação de arquivos."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_PADRAO_DATA = re.compile(r"_(\d{2})-(\d{2})-(\d{4})")


def chave_natural(caminho: Path | str) -> list[object]:
    """Ordenação natural, sem distinção de caixa e de acentos (f2 antes de f10)."""
    texto = Path(caminho).as_posix()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch)).casefold()
    return [int(parte) if parte.isdigit() else parte for parte in re.split(r"(\d+)", texto)]


def chave_por_data(caminho: Path | str) -> tuple[str, list[object]]:
    """Ordenação cronológica pela data _DD-MM-AAAA no nome do arquivo.

    Arquivos sem data vêm primeiro; empates são resolvidos pela ordem natural.
    """
    caminho = Path(caminho)
    encontrado = _PADRAO_DATA.search(caminho.name)
    if encontrado:
        dia, mes, ano = encontrado.groups()
        data = f"{ano}-{mes}-{dia}"
    else:
        data = "0000-00-00"
    return data, chave_natural(caminho)
