"""Identifica artigos em PDF pela Crossref e os renomeia de forma padronizada.

Para cada PDF da pasta, procura o DOI no texto e nos metadados; se nenhum
DOI for validado, busca pelo título. Um registro só é aceito quando o título
(fração de palavras encontradas no PDF, limiar ajustável) e o primeiro autor
conferem com o texto. Preprints são resolvidos para a versão publicada quando
a Crossref indica a relação.

Nome padronizado:
    [TAG_]SOBRENOME_ANO_Titulo_com_sublinhados[_PREPRINT].pdf

TAG é acrescentada quando um autor destacado (por exemplo, a orientadora)
consta do registro. Duplicados (mesmo DOI) são movidos para a pasta de
controle, onde também ficam o relatório e o log de renomeações.

Uso:
    organizar-referencias PASTA [--aplicar] [--controle PASTA_CONTROLE]
                                [--destacar SOBRENOME,NOME,TAG] [--doi ARQUIVO.pdf=10.xxxx/yyy]

Sem --aplicar, apenas gera o relatório (simulação).

Derivado de organizar_referencias.ipynb (Dissertacao, versão 3.1).
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

RE_DOI = re.compile(r'10\.\d{4,9}/[^\s"<>\]]+', re.I)
STOP = {"with", "from", "that", "this", "into", "over", "under", "between", "their",
        "based", "using", "about", "were", "have", "which", "during", "after", "across"}
MARCAS_PREPRINT = ("this is a preprint", "has not been peer reviewed", "has not been peer-reviewed",
                   "not yet been peer reviewed", "preprint submitted to")
METODOS_VALIDOS = ("doi_no_pdf", "busca_titulo", "forcado")

_SESSAO = None


def _sessao():
    """Sessão HTTP com novas tentativas (criada na primeira consulta)."""
    global _SESSAO
    if _SESSAO is None:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        _SESSAO = requests.Session()
        _SESSAO.headers["User-Agent"] = "utilitarios-academicos/organizar-referencias"
        _SESSAO.mount("https://", HTTPAdapter(max_retries=Retry(
            total=5, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])))
    return _SESSAO


# ---------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------
def ascii_limpo(texto: str | None) -> str:
    texto = re.sub(r"[‐-―−]", "-", texto or "")
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def limpar_html(texto: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", texto or ""))


def palavras(texto: str | None) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", ascii_limpo(texto).lower()).split()


class TextoPDF:
    """Texto das primeiras páginas, metadados e título visual (maior fonte) de um PDF."""

    def __init__(self, caminho: Path, n_paginas: int = 3, min_chars: int = 200):
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        documento = fitz.open(caminho)
        todas = [documento[i].get_text() for i in range(min(n_paginas + 2, documento.page_count))]
        self.inicio = next((i for i, t in enumerate(todas) if len(t.strip()) >= min_chars), 0)
        self.paginas = todas[self.inicio:self.inicio + n_paginas]
        metadados = documento.metadata or {}
        self.meta_titulo = metadados.get("title") or ""
        self.meta_autor = metadados.get("author") or ""
        self.meta = " ".join(str(v) for v in metadados.values() if v) + " " + (documento.get_xml_metadata() or "")
        self.titulo_visual = self._titulo_por_fonte(documento[self.inicio]) if documento.page_count else ""
        documento.close()
        bruto = " ".join(self.paginas) + " " + self.meta_autor
        self.conjunto = set(palavras(bruto))
        self.colado = "".join(palavras(bruto))
        baixo = " ".join(palavras(" ".join(self.paginas)))
        self.marca_preprint = any(" ".join(palavras(m)) in baixo for m in MARCAS_PREPRINT)

    @staticmethod
    def _titulo_por_fonte(pagina) -> str:
        spans = [s for b in pagina.get_text("dict")["blocks"] for linha in b.get("lines", [])
                 for s in linha["spans"] if len(s["text"].strip()) > 3]
        if not spans:
            return ""
        maior = max(s["size"] for s in spans)
        return " ".join(s["text"].strip() for s in spans if s["size"] >= maior - 0.5)[:300]

    def contem(self, termo: str) -> bool:
        return termo in self.conjunto or (len(termo) >= 5 and termo in self.colado)

    def candidatos_doi(self) -> list[str]:
        vistos: list[str] = []
        for fonte in [self.meta] + self.paginas:
            fonte = re.sub(r"(10\.\d{4,9}/)\s+", r"\1", fonte)
            for doi in RE_DOI.findall(fonte):
                doi = doi.rstrip(".,;:").lower()
                while doi.endswith(")") and doi.count("(") < doi.count(")"):
                    doi = doi[:-1]
                if doi not in vistos:
                    vistos.append(doi)
        return vistos[:15]

    def consultas(self) -> list[str]:
        consultas = []
        if self.meta_titulo:
            consultas.append(f"{self.meta_titulo} {self.meta_autor}")
        if self.titulo_visual:
            consultas.append(f"{self.titulo_visual} {self.meta_autor}")
        if self.paginas:
            consultas.append(" ".join([w for w in self.paginas[0].split() if len(w) >= 3][:80]))
        return [" ".join(palavras(c))[:300] for c in consultas if c.strip()]


# ---------------------------------------------------------------------
# Crossref
# ---------------------------------------------------------------------
def crossref_doi(doi: str) -> dict | None:
    from requests.utils import quote

    try:
        resposta = _sessao().get(f"https://api.crossref.org/works/{quote(doi, safe='/')}", timeout=30)
        time.sleep(0.2)
        return resposta.json()["message"] if resposta.ok else None
    except Exception:
        return None


def crossref_busca(consulta: str, n: int = 5) -> list[dict]:
    try:
        resposta = _sessao().get("https://api.crossref.org/works",
                                 params={"query.bibliographic": consulta, "rows": n}, timeout=30)
        time.sleep(0.2)
        return resposta.json()["message"]["items"] if resposta.ok else []
    except Exception:
        return []


def validar(registro: dict, pdf: TextoPDF) -> tuple[float, bool, bool]:
    """(fração do título encontrada no PDF, primeiro autor encontrado, título contínuo encontrado)."""
    ws = palavras(limpar_html((registro.get("title") or [""])[0]))
    termos = [w for w in ws if len(w) >= 4 and w not in STOP] or [w for w in ws if len(w) >= 3]
    if not termos or not registro.get("author"):
        return 0.0, False, False
    escore = sum(pdf.contem(w) for w in termos) / len(termos)
    primeiro = registro["author"][0]
    autor_ok = any(pdf.contem(w) for w in palavras(primeiro.get("family") or primeiro.get("name")) if len(w) >= 3)
    return escore, autor_ok, "".join(ws) in pdf.colado


def resolver_publicado(registro: dict) -> tuple[dict, bool]:
    """Substitui um preprint pela versão publicada, quando a Crossref a indica."""
    if registro.get("type") != "posted-content":
        return registro, False
    for relacao in (registro.get("relation") or {}).get("is-preprint-of", []):
        if relacao.get("id-type") == "doi" and (publicado := crossref_doi(relacao["id"])):
            return publicado, True
    return registro, True


def identificar(caminho: Path, limiar: float = 0.80, doi_forcado: dict[str, str] | None = None) -> dict:
    pdf = TextoPDF(caminho)
    base = {"registro": None, "metodo": "NAO VALIDADO", "score": 0.0,
            "autor_ok": False, "doi_pdf": "", "preprint": False}
    doi_forcado = doi_forcado or {}
    if caminho.name in doi_forcado and (registro := crossref_doi(doi_forcado[caminho.name])):
        final, preprint = resolver_publicado(registro)
        return {**base, "registro": final, "metodo": "forcado", "score": 1.0, "autor_ok": True,
                "doi_pdf": registro["DOI"], "preprint": preprint or pdf.marca_preprint}
    tentativas = []
    for doi in pdf.candidatos_doi():
        if registro := crossref_doi(doi):
            escore, autor, _ = validar(registro, pdf)
            tentativas.append({"reg": registro, "s": escore, "a": autor,
                               "ok": escore >= limiar and autor, "metodo": "doi_no_pdf"})
    if not any(t["ok"] for t in tentativas):
        for consulta in pdf.consultas():
            for registro in crossref_busca(consulta):
                escore, autor, continuo = validar(registro, pdf)
                tentativas.append({"reg": registro, "s": escore, "a": autor,
                                   "ok": continuo and autor, "metodo": "busca_titulo"})
    validos = [t for t in tentativas if t["ok"]]
    if not validos:
        if tentativas:
            melhor = max(tentativas, key=lambda t: t["s"])
            base.update(score=melhor["s"], doi_pdf=melhor["reg"].get("DOI", ""))
        return base
    melhor = max(validos, key=lambda t: (t["s"], t["reg"].get("type") != "posted-content"))
    final, preprint = resolver_publicado(melhor["reg"])
    preprint = preprint or pdf.marca_preprint or any(t["reg"].get("type") == "posted-content" for t in validos)
    return {**base, "registro": final, "metodo": melhor["metodo"], "score": melhor["s"],
            "autor_ok": melhor["a"], "doi_pdf": melhor["reg"].get("DOI", ""), "preprint": preprint}


# ---------------------------------------------------------------------
# Nome padronizado
# ---------------------------------------------------------------------
def ano(registro: dict) -> int | str:
    for chave in ("issued", "published-print", "published-online", "created"):
        partes = (registro.get(chave) or {}).get("date-parts") or [[None]]
        if partes[0] and partes[0][0]:
            return partes[0][0]
    return "SD"


def tem_autor_destacado(registro: dict | None, destacado: dict | None) -> bool:
    if not destacado:
        return False
    for autor in (registro or {}).get("author", []):
        familia = "".join(palavras(autor.get("family")))
        nome = "".join(palavras(autor.get("given")))
        if destacado["sobrenome"] in familia and nome.startswith(destacado["nome"]):
            return True
    return False


def nome_padrao(registro: dict, preprint: bool = False, destacado: dict | None = None,
                max_titulo: int = 100) -> str:
    primeiro = registro["author"][0]
    sobrenome = re.sub(r"[^A-Z]", "", ascii_limpo(primeiro.get("family") or primeiro.get("name") or "SEMAUTOR").upper())
    titulo = "_".join(re.sub(r"[^A-Za-z0-9\- ]+", " ", ascii_limpo(limpar_html(registro["title"][0]))).split())
    if len(titulo) > max_titulo:
        titulo = titulo[:max_titulo].rsplit("_", 1)[0]
    tag = f"{destacado['tag']}_" if tem_autor_destacado(registro, destacado) else ""
    return f"{tag}{sobrenome}_{ano(registro)}_{titulo}{'_PREPRINT' if preprint else ''}.pdf"


# ---------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------
def organizar(pasta: Path, controle: Path, simular: bool = True, limiar: float = 0.80,
              max_titulo: int = 100, destacado: dict | None = None,
              doi_forcado: dict[str, str] | None = None):
    """Identifica, gera o relatório e, se `simular` for falso, renomeia e move duplicados."""
    import pandas as pd

    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta não encontrada: {pasta}")
    controle.mkdir(parents=True, exist_ok=True)
    duplicados = controle / "_duplicados"
    log = controle / "_log_renomeacao.csv"
    relatorio = controle / "_relatorio_referencias.csv"

    pdfs = sorted(pasta.glob("*.pdf"))
    linhas = []
    for i, caminho in enumerate(pdfs, 1):
        print(f"[{i:02d}/{len(pdfs)}] {caminho.name[:80]}")
        try:
            r = identificar(caminho, limiar, doi_forcado)
        except Exception as erro:
            r = {"registro": None, "metodo": f"ERRO: {erro}", "score": 0.0,
                 "autor_ok": False, "doi_pdf": "", "preprint": False}
        registro = r["registro"]
        valido = r["metodo"] in METODOS_VALIDOS
        linhas.append({
            "status": "OK" if valido else "REVISAR",
            "autor_destacado": tem_autor_destacado(registro, destacado),
            "preprint": r["preprint"], "metodo": r["metodo"],
            "score_titulo": round(r["score"], 2), "autor_no_pdf": r["autor_ok"],
            "arquivo_atual": caminho.name,
            "nome_novo": nome_padrao(registro, r["preprint"], destacado, max_titulo) if (registro and valido) else "",
            "doi_pdf": r["doi_pdf"], "doi_final": (registro or {}).get("DOI", "").lower(),
            "tamanho_mb": round(caminho.stat().st_size / 1e6, 1),
        })

    df = pd.DataFrame(linhas)
    if df.empty:
        print("Nenhum PDF encontrado.")
        return df
    prioridade = {"forcado": 0, "doi_no_pdf": 0, "busca_titulo": 1}
    for _, grupo in df[df.status == "OK"].groupby("doi_final"):
        if len(grupo) > 1:
            ordem = grupo.assign(r=grupo.metodo.map(prioridade)).sort_values(
                ["preprint", "r", "tamanho_mb"], ascending=[True, True, False])
            df.loc[ordem.index[1:], "status"] = "DUPLICADO"
    df.loc[(df.status == "OK") & (df.arquivo_atual == df.nome_novo), "status"] = "JA PADRONIZADO"
    df.to_csv(relatorio, index=False, encoding="utf-8")
    print(df.drop(columns=["tamanho_mb"]).to_string(index=False))

    renomear, mover = df[df.status == "OK"], df[df.status == "DUPLICADO"]
    if simular:
        print(f"\nSimulação: {len(renomear)} renomeações e {len(mover)} duplicados a mover. Nada alterado.")
    else:
        duplicados.mkdir(exist_ok=True)
        agora, novo_log = f"{datetime.now():%Y-%m-%d %H:%M}", not log.exists()
        with open(log, "a", newline="", encoding="utf-8") as f:
            escritor = csv.writer(f)
            if novo_log:
                escritor.writerow(["data", "acao", "nome_original", "nome_novo", "doi_final", "metodo"])
            for _, r in mover.iterrows():
                destino = duplicados / r.arquivo_atual
                if destino.exists():
                    destino = duplicados / f"{destino.stem}_{datetime.now():%H%M%S}.pdf"
                (pasta / r.arquivo_atual).rename(destino)
                escritor.writerow([agora, "movido_duplicado", r.arquivo_atual,
                                   f"_duplicados/{destino.name}", r.doi_final, r.metodo])
            for _, r in renomear.iterrows():
                destino = pasta / r.nome_novo
                if destino.exists():
                    print("PULADO, destino já existe:", r.nome_novo)
                    continue
                (pasta / r.arquivo_atual).rename(destino)
                escritor.writerow([agora, "renomeado", r.arquivo_atual, r.nome_novo, r.doi_final, r.metodo])
        print(f"\nAplicado: {len(renomear)} renomeados, {len(mover)} movidos para {duplicados}. Log: {log}")

    pendentes = df[df.status.isin(["REVISAR", "DUPLICADO"])]
    if len(pendentes):
        print("\nPENDENTES E DUPLICADOS:")
        print(pendentes[["status", "arquivo_atual", "doi_final", "metodo", "score_titulo"]].to_string(index=False))
    return df


def _destacado(texto: str | None) -> dict | None:
    if not texto:
        return None
    partes = [p.strip() for p in texto.split(",")]
    if len(partes) != 3 or not all(partes):
        raise argparse.ArgumentTypeError("use SOBRENOME,NOME,TAG (ex.: rodrigues,regina,REGINA)")
    sobrenome, nome, tag = partes
    return {"sobrenome": "".join(palavras(sobrenome)), "nome": "".join(palavras(nome)), "tag": tag}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="organizar-referencias", description=__doc__.splitlines()[0])
    parser.add_argument("pasta", type=Path, help="pasta com os PDFs")
    parser.add_argument("--controle", type=Path, help="pasta de relatório, log e duplicados (padrão: PASTA/_controle)")
    parser.add_argument("--aplicar", action="store_true", help="renomeia e move (sem esta opção, apenas simula)")
    parser.add_argument("--limiar", type=float, default=0.80, help="fração mínima do título encontrada no PDF")
    parser.add_argument("--max-titulo", type=int, default=100, help="caracteres máximos do título no nome")
    parser.add_argument("--destacar", type=_destacado, help="SOBRENOME,NOME,TAG de um autor a destacar no nome")
    parser.add_argument("--doi", action="append", default=[], metavar="ARQUIVO.pdf=DOI",
                        help="força o DOI de um arquivo (repetível)")
    args = parser.parse_args(argv)
    doi_forcado = {}
    for item in args.doi:
        arquivo, _, doi = item.partition("=")
        if not doi:
            parser.error(f"--doi inválido: {item}")
        doi_forcado[arquivo] = doi
    try:
        organizar(args.pasta, args.controle or args.pasta / "_controle", simular=not args.aplicar,
                  limiar=args.limiar, max_titulo=args.max_titulo, destacado=args.destacar,
                  doi_forcado=doi_forcado)
    except Exception as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
