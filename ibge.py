"""
ibge.py — ROBÔ DE PESOS: coleta variação e peso mensal por grupo/subgrupo do
IPCA (API SIDRA/IBGE).

O SGS do Banco Central não publica peso (participação na cesta) por grupo —
só o IBGE, que calcula o índice, tem essa informação (tabela 7060 do SIDRA).
É a combinação peso x variação (contribuição, em pontos percentuais) que
permite dizer quem de fato "puxou" o IPCA no mês, em vez de comparar
variações brutas de grupos com pesos muito diferentes.

Endpoint (confirmado):
  https://apisidra.ibge.gov.br/values/t/7060/n1/1/v/63,66,2265/p/last%201/
  c315/{códigos}?formato=json

Guardamos só o mês mais recente disponível — a série histórica de variação
do IPCA cheio já vem do SGS (ipca_geral); aqui o interesse é a fotografia
(peso + variação) do mês corrente por grupo e subgrupo.
"""

import logging
import time
from datetime import datetime

import requests

import config
import db

log = logging.getLogger("ibge")


def _consultar_sidra(codigos):
    url = config.IBGE_SIDRA_BASE_URL.format(
        variaveis=config.IBGE_SIDRA_VARIAVEIS,
        codigos=",".join(str(c) for c in codigos),
    )
    ultimo_erro = None
    for tentativa in range(1, config.HTTP_TENTATIVAS + 1):
        try:
            resp = requests.get(url, params={"formato": "json"}, timeout=config.HTTP_TIMEOUT)
            resp.raise_for_status()
            dados = resp.json()
            return dados[1:] if len(dados) > 1 else []
        except Exception as e:  # noqa: BLE001
            ultimo_erro = e
            espera = config.HTTP_BACKOFF * tentativa
            log.warning("SIDRA falhou (tentativa %d/%d): %s — aguardando %.1fs",
                        tentativa, config.HTTP_TENTATIVAS, e, espera)
            time.sleep(espera)
    raise RuntimeError(f"Falha ao consultar SIDRA em {url}. Último erro: {ultimo_erro}")


def coletar(offline=False):
    """
    Coleta variação mensal, peso mensal e variação em 12 meses dos grupos e
    subgrupos do IPCA (mês mais recente disponível) e grava em `ipca_grupos`.
    """
    db.inicializar()
    catalogo = {**config.IBGE_GRUPOS, **config.IBGE_SUBGRUPOS}

    if offline:
        linhas = _dados_sinteticos(catalogo)
    else:
        valores = _consultar_sidra(list(catalogo.keys()))
        por_codigo = {}
        mes_ref = None
        for item in valores:
            valor = item["V"]
            if valor in (None, "...", "-"):
                continue
            codigo = int(item["D4C"])
            periodo = item["D3C"]  # AAAAMM
            mes_ref = f"{periodo[:4]}-{periodo[4:]}-01"
            slot = por_codigo.setdefault(codigo, {})
            var_id = item["D2C"]
            if var_id == "63":
                slot["variacao_mensal"] = float(valor)
            elif var_id == "66":
                slot["peso_mensal"] = float(valor)
            elif var_id == "2265":
                slot["variacao_12m"] = float(valor)

        linhas = []
        for codigo, vals in por_codigo.items():
            if codigo not in catalogo:
                continue
            grupo_numero, nome = catalogo[codigo]
            nivel = "grupo" if codigo in config.IBGE_GRUPOS else "subgrupo"
            linhas.append((
                mes_ref, nivel, codigo, grupo_numero, nome,
                vals.get("variacao_mensal"), vals.get("peso_mensal"), vals.get("variacao_12m"),
            ))

    if linhas:
        db.salvar_ipca_grupos(linhas)
        log.info("IBGE/SIDRA: %d grupos/subgrupos gravados (mês %s).",
                  len(linhas), linhas[0][0])
    else:
        log.warning("IBGE/SIDRA: nenhum dado retornado nesta coleta.")
    return linhas


# ---------------------------------------------------------------------------
# Fallback sintético — só para demonstração/testes offline.
# NÃO use estes números para análise real.
# ---------------------------------------------------------------------------
def _dados_sinteticos(catalogo):
    import random

    random.seed(42)
    mes_ref = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    linhas = []
    for codigo, (grupo_numero, nome) in catalogo.items():
        nivel = "grupo" if codigo in config.IBGE_GRUPOS else "subgrupo"
        peso = round(random.uniform(2, 20), 4) if nivel == "grupo" else round(random.uniform(0.5, 10), 4)
        var = round(random.uniform(-1.0, 1.0), 2)
        linhas.append((mes_ref, nivel, codigo, grupo_numero, nome, var, peso, var * 6))
    return linhas


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    coletar(offline="--offline" in sys.argv)
