"""
tratamento.py — ROBÔ 2: TRATAMENTO E LIMPEZA.

Responsabilidade única: transformar o dado bruto do SQLite em um DataFrame
limpo, com datas normalizadas, sem duplicatas e com buracos sinalizados.

Este é exatamente o "trabalho braçal" que some da sua rotina quando é
delegado a um agente. As regras aqui são explícitas e auditáveis — nada
de "achismo": se uma observação é descartada, fica registrado o porquê.
"""

import logging
import pandas as pd

import db

log = logging.getLogger("tratamento")


def carregar(serie):
    """Lê uma série do SQLite e devolve um DataFrame mensal limpo."""
    registros = db.ler_serie(serie)
    if not registros:
        raise ValueError(f"Série '{serie}' não encontrada no banco. Rode a coleta antes.")

    df = pd.DataFrame(registros, columns=["data", "valor"])
    df["data"] = pd.to_datetime(df["data"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")

    antes = len(df)
    # 1) Remove valores impossíveis de parsear.
    df = df.dropna(subset=["valor"])
    # 2) Remove duplicatas de data (mantém a última — que é a revisada).
    df = df.drop_duplicates(subset="data", keep="last")
    # 3) Ordena.
    df = df.sort_values("data").reset_index(drop=True)
    descartadas = antes - len(df)
    if descartadas:
        log.info("Série '%s': %d observações descartadas na limpeza.", serie, descartadas)

    return df


def para_mensal(df):
    """
    Reamostra para frequência mensal (fim de mês) e sinaliza buracos.
    Séries diárias (câmbio) viram média mensal; mensais ficam como estão.
    """
    s = df.set_index("data")["valor"]
    # Média no mês resolve tanto diário->mensal quanto duplicidades residuais.
    mensal = s.resample("MS").mean()
    buracos = int(mensal.isna().sum())
    if buracos:
        log.warning("%d mês(es) sem dado — interpolação linear aplicada.", buracos)
        mensal = mensal.interpolate(method="linear", limit_direction="both")
    return mensal


def sanidade(mensal, serie):
    """
    Checagens simples que pegam 90% dos erros silenciosos de API:
    - série vazia
    - salto absurdo (possível erro de unidade / vírgula decimal)
    Retorna lista de alertas (vazia = tudo ok).
    """
    alertas = []
    if mensal.empty:
        alertas.append(f"[{serie}] série vazia após tratamento.")
        return alertas
    variacao = mensal.pct_change().abs()
    suspeitos = variacao[variacao > 5].dropna()  # >500% de um mês p/ outro
    for data, v in suspeitos.items():
        alertas.append(f"[{serie}] salto suspeito em {data:%Y-%m}: {v*100:.0f}% — conferir fonte.")
    return alertas


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import config
    for serie in config.SERIES:
        try:
            df = carregar(serie)
            mensal = para_mensal(df)
            for a in sanidade(mensal, serie):
                log.warning(a)
            log.info("Série '%s' tratada: %d pontos, de %s a %s.",
                     serie, len(mensal), mensal.index.min(), mensal.index.max())
        except Exception as e:
            log.error("Falha ao tratar '%s': %s", serie, e)
