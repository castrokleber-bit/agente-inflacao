"""
coleta.py — ROBÔ 1: COLETA DE DADOS.

Responsabilidade única: varrer a API do Banco Central (SGS) e gravar os
dados brutos no SQLite. Nada de limpeza sofisticada aqui — só trazer para casa.

Dois pontos de "engenharia de produção" que fazem diferença:

1. Retentativa com backoff: APIs públicas caem, dão timeout, retornam 500.
   Em vez de o pipeline morrer, tentamos de novo algumas vezes.

2. Erros DESCRITIVOS: quando algo quebra, a mensagem diz exatamente qual
   série, qual URL e qual status. Isso é o que permite o padrão
   "script que se autocorrige": você cola o traceback no Claude e ele tem
   contexto suficiente para propor a correção (ou o próprio agente lê o log).
"""

import time
import logging
from datetime import datetime

import requests

import config
import db

log = logging.getLogger("coleta")


def _url(codigo, dias_anos):
    inicio = datetime.now().replace(year=datetime.now().year - config.HISTORICO_ANOS)
    return config.SGS_BASE_URL.format(codigo=codigo), {
        "formato": "json",
        "dataInicial": inicio.strftime("%d/%m/%Y"),
        "dataFinal": datetime.now().strftime("%d/%m/%Y"),
    }


def _baixar_sgs(codigo):
    """Baixa uma série do SGS com retentativa. Levanta exceção clara se falhar."""
    url, params = _url(codigo, config.HISTORICO_ANOS)
    ultimo_erro = None
    for tentativa in range(1, config.HTTP_TENTATIVAS + 1):
        try:
            resp = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # noqa: BLE001 (queremos capturar tudo e reportar)
            ultimo_erro = e
            espera = config.HTTP_BACKOFF * tentativa
            log.warning("SGS %s falhou (tentativa %d/%d): %s — aguardando %.1fs",
                        codigo, tentativa, config.HTTP_TENTATIVAS, e, espera)
            time.sleep(espera)
    raise RuntimeError(
        f"Falha ao baixar série SGS {codigo} em {url} após "
        f"{config.HTTP_TENTATIVAS} tentativas. Último erro: {ultimo_erro}"
    )


def _para_iso(data_br):
    """Converte 'dd/mm/aaaa' -> 'aaaa-mm-dd'. Datas do SGS vêm em pt-BR."""
    return datetime.strptime(data_br, "%d/%m/%Y").strftime("%Y-%m-%d")


def coletar(offline=False):
    """
    Coleta todas as séries de config.SERIES e grava no SQLite.

    offline=True usa dados sintéticos (para testar o pipeline sem internet
    ou quando a API está fora). Em produção, rode com offline=False.
    """
    db.inicializar()
    total = 0
    for serie, (codigo, descricao) in config.SERIES.items():
        db.registrar_serie(serie, codigo, descricao)
        if offline:
            registros = _dados_sinteticos(serie)
        else:
            bruto = _baixar_sgs(codigo)
            registros = [
                (_para_iso(item["data"]), float(item["valor"]))
                for item in bruto
                if item.get("valor") not in (None, "")
            ]
        db.salvar_observacoes(serie, registros)
        log.info("Série '%s' (SGS %s): %d observações gravadas.", serie, codigo, len(registros))
        total += len(registros)
    log.info("Coleta concluída: %d observações no total.", total)
    return total


# ---------------------------------------------------------------------------
# Fallback sintético — só para demonstração/testes offline.
# NÃO use estes números para análise real.
# ---------------------------------------------------------------------------
def _dados_sinteticos(serie):
    import random
    from dateutil.relativedelta import relativedelta

    random.seed(hash(serie) % 10_000)
    hoje = datetime.now().replace(day=1)
    n = config.HISTORICO_ANOS * 12
    base = {
        "ipca_mensal": 0.45, "ipca_12m": 4.5, "ipca_nucleo_ms": 0.40,
        "inpc_mensal": 0.42, "igpm_mensal": 0.35, "selic_meta": 11.0,
        "cambio_venda": 5.3,
    }.get(serie, 0.4)
    registros = []
    valor = base
    for i in range(n, 0, -1):
        d = (hoje - relativedelta(months=i)).strftime("%Y-%m-%d")
        if serie == "selic_meta":
            valor = max(6.5, min(14.75, valor + random.choice([-0.25, 0, 0, 0.25])))
        elif serie == "cambio_venda":
            valor = max(4.5, min(6.2, valor + random.uniform(-0.15, 0.15)))
        elif serie == "ipca_12m":
            valor = max(2.0, min(9.0, valor + random.uniform(-0.3, 0.3)))
        else:
            valor = max(-0.2, min(1.6, base + random.uniform(-0.35, 0.55)))
        registros.append((d, round(valor, 4)))
    return registros


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    coletar(offline="--offline" in sys.argv)
