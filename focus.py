"""
focus.py — ROBÔ DE EXPECTATIVAS: coleta a mediana do Focus (API Olinda).

Para a PREVISÃO do IPCA geral, a referência de mercado é a mediana das
expectativas anuais do Boletim Focus, publicada pelo BC via API Olinda
(padrão OData). É isso que substitui a projeção ingênua do template inicial.

Endpoint (confirmado):
  https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/
  ExpectativasMercadoAnuais?$format=json&$filter=...&$select=...&$orderby=Data desc

Campos retornados: Indicador, Data (dia da divulgação), DataReferencia (ano
projetado), Media, Mediana, DesvioPadrao, Minimo, Maximo, numeroRespondentes,
baseCalculo (0 = expectativa do dia; 1 = média dos últimos 5 dias úteis).

Estratégia: pegamos, para o indicador IPCA e baseCalculo 0, a mediana mais
recente de cada ano de referência (ano corrente + próximos), e gravamos em
`focus_ipca`. A projeção do agente passa a ser "a mediana do Focus", auditável.
"""

import logging
import time
from datetime import datetime
from urllib.parse import quote, urlencode

import requests

import config
import db

log = logging.getLogger("focus")


def _consultar_olinda(ano_ref):
    """Consulta a mediana anual do IPCA para um ano de referência específico."""
    url = config.FOCUS_BASE_URL.format(recurso=config.FOCUS_RECURSO_ANUAL)
    params = {
        "$format": "json",
        "$filter": (
            f"Indicador eq '{config.FOCUS_INDICADOR}' "
            f"and DataReferencia eq '{ano_ref}' "
            f"and baseCalculo eq {config.FOCUS_BASE_CALCULO}"
        ),
        "$orderby": "Data desc",
        "$top": 1,  # só a divulgação mais recente
        "$select": "Indicador,Data,DataReferencia,Media,Mediana,Minimo,Maximo",
    }
    # O serviço OData da Olinda trata "+" como caractere literal (não como
    # espaço) dentro do $filter, quebrando o parser da expressão. requests
    # usa quote_plus (espaço -> "+") por padrão em params=; forçamos "%20"
    # montando a query string nós mesmos.
    query = urlencode(params, quote_via=quote)
    ultimo_erro = None
    for tentativa in range(1, config.HTTP_TENTATIVAS + 1):
        try:
            resp = requests.get(f"{url}?{query}", timeout=config.HTTP_TIMEOUT)
            resp.raise_for_status()
            valores = resp.json().get("value", [])
            return valores[0] if valores else None
        except Exception as e:  # noqa: BLE001
            ultimo_erro = e
            espera = config.HTTP_BACKOFF * tentativa
            log.warning("Focus %s falhou (tentativa %d/%d): %s — aguardando %.1fs",
                        ano_ref, tentativa, config.HTTP_TENTATIVAS, e, espera)
            time.sleep(espera)
    raise RuntimeError(
        f"Falha ao consultar Focus (ano {ano_ref}) em {url}. Último erro: {ultimo_erro}"
    )


def coletar(offline=False):
    """Coleta a mediana do Focus para o ano corrente e os seguintes."""
    db.inicializar()
    ano0 = datetime.now().year
    anos = [ano0 + i for i in range(config.FOCUS_ANOS_PROJECAO)]
    registros = []
    for ano in anos:
        item = _dado_sintetico_focus(ano) if offline else _consultar_olinda(ano)
        if not item:
            log.warning("Focus sem dado para %s — pulando.", ano)
            continue
        registros.append((
            item["Data"], int(item["DataReferencia"]),
            item.get("Mediana"), item.get("Media"),
            item.get("Minimo"), item.get("Maximo"),
        ))
        log.info("Focus %s: mediana %.2f%% (divulgado em %s).",
                 ano, item.get("Mediana", float("nan")), item["Data"])
    if registros:
        db.salvar_focus(registros)
    return registros


def projecao_ano_corrente():
    """Retorna (ano, mediana, data_divulgacao) do Focus para o ano corrente, ou None."""
    ano0 = datetime.now().year
    for ano, mediana, data_coleta in db.focus_mais_recente():
        if ano == ano0:
            return ano, mediana, data_coleta
    return None


# ---------------------------------------------------------------------------
# Fallback sintético — só para demonstração offline.
# ---------------------------------------------------------------------------
def _dado_sintetico_focus(ano):
    base = {0: 4.6, 1: 4.0, 2: 3.7}.get(ano - datetime.now().year, 3.5)
    return {
        "Indicador": "IPCA", "Data": datetime.now().strftime("%Y-%m-%d"),
        "DataReferencia": str(ano), "Mediana": base, "Media": base + 0.05,
        "Minimo": base - 0.8, "Maximo": base + 0.9,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    coletar(offline="--offline" in sys.argv)
    print("Projeção Focus (ano corrente):", projecao_ano_corrente())
