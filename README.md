# utilitarios-academicos

Ferramentas de linha de comando para tarefas recorrentes em trabalhos acadêmicos: compilar documentos em um único PDF, converter arquivos para PDF, montar mosaicos e animações de figuras e padronizar a nomeação de artigos pela Crossref.

## Instalação

```bash
pip install "utilitarios-academicos @ git+https://github.com/Diass99/utilitarios-academicos"
# com os extras de referências (Crossref) e de vídeo (MP4)
pip install "utilitarios-academicos[referencias,video] @ git+https://github.com/Diass99/utilitarios-academicos"
```

`juntar-documentos` e `converter-para-pdf` usam o LibreOffice para arquivos Office e de código (`sudo apt install libreoffice`).

## Ferramentas

| Comando | Função | Extra |
|---|---|---|
| `juntar-documentos` | compila PDFs, imagens, arquivos Office e códigos de uma pasta em um único PDF, com capa por arquivo e sumário | |
| `converter-para-pdf` | converte um arquivo, ou todos os de uma pasta, para PDF | |
| `criar-mosaico` | monta uma grade de figuras, centralizadas sobre fundo branco | |
| `criar-animacao` | gera GIF ou MP4 a partir de uma sequência de figuras | `video` (MP4) |
| `organizar-referencias` | identifica artigos em PDF pela Crossref e os renomeia como `SOBRENOME_ANO_Titulo.pdf` | `referencias` |

## Exemplos

```bash
# Compilação em ordem cronológica (data _DD-MM-AAAA no nome dos arquivos)
juntar-documentos ~/comentarios --ordem data --saida comentarios.pdf

# Mosaico 2 × 3 das figuras PNG de uma pasta
criar-mosaico figuras/ --colunas 2 --linhas 3 --saida mosaico.png

# Animação de saídas horárias do WRF a cada 6 h, sem o instante inicial
criar-animacao figuras/ --saida precipitacao.mp4 --passo 6 --pular-primeiro --duracao-ms 500

# Referências: simulação (relatório apenas) e, após conferência, aplicação
organizar-referencias referencias/ --destacar rodrigues,regina,REGINA
organizar-referencias referencias/ --destacar rodrigues,regina,REGINA --aplicar
```

`organizar-referencias` grava o relatório (`_relatorio_referencias.csv`), o log de renomeações e os duplicados na pasta de controle (padrão: `PASTA/_controle`; altere com `--controle`). Sem `--aplicar`, nenhum arquivo é modificado. No Google Colab, basta instalar o pacote com o extra `referencias` e executar o comando sobre a pasta do Drive montada.

## Estrutura

```text
utilitarios-academicos/
├── src/utilitarios_academicos/
│   ├── ordenacao.py                ordem natural e por data
│   ├── pdf/                        juntar_documentos, converter_para_pdf
│   ├── figuras/                    criar_mosaico, criar_animacao
│   └── referencias/                organizar_referencias
├── tests/
├── pyproject.toml
├── MANIFESTO.tsv                   origem de cada módulo
├── LICENSE
└── README.md
```

## Testes

```bash
pip install -e ".[dev,referencias,video]"
pytest
```

Os testes não exigem rede nem LibreOffice.

## Autor

Vinícius José Dias, Programa de Pós-Graduação em Oceanografia (PPGOceano/UFSC).

## Licença

Código distribuído sob a licença MIT. Ver [`LICENSE`](LICENSE).
