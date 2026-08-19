"""
modelagem.py — ROBÔ 3: MODELAGEM E CÁLCULO.

Pega as séries limpas e produz os indicadores que um analista de inflação
de fato usa, agora com os recortes que a GPE acompanha:
  - IPCA geral: no mês, no ano, 12 meses, momentum (mm3 anualizada)
  - Serviços e difusão (leitura de espraiamento/estruturalidade)
  - Média dos núcleos em 12 meses (tendência subjacente)
  - Desvio em relação à meta
  - PROJEÇÃO = mediana do Focus (via Olinda), não mais um chute ingênuo

Tudo relevante é gravado na tabela `indicadores` para o dashboard/relatório.
"""

import logging
import pandas as pd

import config
import db
import tratamento
import focus

log = logging.getLogger("modelagem")


def _acumulado_composto(serie_mensal):
    return ((1 + serie_mensal / 100).cumprod() - 1) * 100


def _rolling_12m(serie_mensal):
    return (
        serie_mensal.rolling(12)
        .apply(lambda x: ((1 + x / 100).prod() - 1) * 100, raw=True)
        .dropna()
    )


def _serie_mensal(nome):
    return tratamento.para_mensal(tratamento.carregar(nome))


def media_nucleos_12m():
    """Média em 12 meses dos núcleos disponíveis — proxy de tendência do BC."""
    series_12m = []
    for nome in config.NUCLEOS:
        try:
            series_12m.append(_rolling_12m(_serie_mensal(nome)).rename(nome))
        except Exception as e:  # série pode faltar; seguimos com as demais
            log.warning("Núcleo '%s' indisponível: %s", nome, e)
    if not series_12m:
        return pd.Series(dtype=float)
    return pd.concat(series_12m, axis=1).mean(axis=1)


def movimentos_ibge(indice="ipca"):
    """
    Contribuição em pontos percentuais (peso/100 * variação) de cada grupo
    do IPCA (ou IPCA-15, indice="ipca15") no mês mais recente coletado do
    IBGE/SIDRA — quem de fato "puxou" o índice, e não apenas quem teve a
    maior variação bruta. Para cada grupo destacado, também aponta o
    subgrupo de maior contribuição (em módulo) dentro dele.
    """
    linhas = db.ipca_grupos_mes_mais_recente(indice=indice)
    grupos, subgrupos_por_grupo = [], {}
    for _mes, nivel, _codigo, grupo_numero, nome, var, peso, var_12m in linhas:
        if var is None or peso is None:
            continue
        registro = {
            "grupo_numero": grupo_numero, "nome": nome, "variacao": var,
            "peso": peso, "contribuicao": peso / 100 * var, "variacao_12m": var_12m,
        }
        if nivel == "grupo":
            grupos.append(registro)
        else:
            subgrupos_por_grupo.setdefault(grupo_numero, []).append(registro)

    if not grupos:
        return {"peso_grupo_nome": None, "peso_grupo_12m": float("nan"),
                "grupos_altas": [], "grupos_quedas": []}

    for g in grupos:
        candidatos = subgrupos_por_grupo.get(g["grupo_numero"], [])
        g["subgrupo_principal"] = (
            max(candidatos, key=lambda s: abs(s["contribuicao"])) if candidatos else None
        )

    ranking = sorted(grupos, key=lambda g: g["contribuicao"], reverse=True)
    grupo_mais_pesado = max(grupos, key=lambda g: g["peso"])

    return {
        "peso_grupo_nome": grupo_mais_pesado["nome"],
        "peso_grupo_12m": grupo_mais_pesado["variacao_12m"],
        "grupos_altas": [g for g in ranking if g["contribuicao"] > 0][:2],
        "grupos_quedas": sorted(
            (g for g in ranking if g["contribuicao"] < 0),
            key=lambda g: g["contribuicao"],
        )[:2],
    }


def calcular_ipca():
    mensal = _serie_mensal("ipca_geral")

    ano_atual = mensal.index.max().year
    no_ano = mensal[mensal.index.year == ano_atual]
    ipca_12m = _rolling_12m(mensal)
    mm3_anual = ((1 + mensal.rolling(3).mean() / 100) ** 12 - 1) * 100

    # Recortes adicionais (tolerantes a ausência de série)
    def _ultimo_12m(nome):
        try:
            return float(_rolling_12m(_serie_mensal(nome)).iloc[-1])
        except Exception as e:
            log.warning("Recorte '%s' indisponível: %s", nome, e)
            return float("nan")

    def _ultimo_nivel(nome):
        try:
            return float(_serie_mensal(nome).iloc[-1])
        except Exception as e:
            log.warning("Série '%s' indisponível: %s", nome, e)
            return float("nan")

    nucleos_12m = media_nucleos_12m()
    ultimo_mes = mensal.index.max()

    r = {
        "indice": "ipca",
        "referencia": ultimo_mes,
        "no_mes": float(mensal.iloc[-1]),
        "no_ano": float(_acumulado_composto(no_ano).iloc[-1]) if len(no_ano) else float("nan"),
        "em_12m": float(ipca_12m.iloc[-1]) if len(ipca_12m) else float("nan"),
        "mm3_anualizada": float(mm3_anual.iloc[-1]) if len(mm3_anual.dropna()) else float("nan"),
        "servicos_12m": _ultimo_12m("ipca_servicos"),
        "nucleos_12m": float(nucleos_12m.iloc[-1]) if len(nucleos_12m) else float("nan"),
        "difusao": _ultimo_nivel("ipca_difusao"),
        "meta": config.META_INFLACAO,
        "banda": config.META_TOLERANCIA,
        "serie_mensal": mensal,
        "serie_12m": ipca_12m,
        "serie_nucleos_12m": nucleos_12m,
    }
    r["desvio_meta"] = r["em_12m"] - config.META_INFLACAO
    r["dentro_banda"] = abs(r["desvio_meta"]) <= config.META_TOLERANCIA

    # Peso e contribuição por grupo do IPCA (IBGE/SIDRA) — quem puxou o
    # índice no mês, e o grupo de maior peso na cesta (para contextualizar
    # ao lado de serviços no comentário).
    r.update(movimentos_ibge(indice="ipca"))

    # Projeção = mediana do Focus para o ano corrente (fonte auditável).
    proj = focus.projecao_ano_corrente(indicador=config.FOCUS_INDICADOR_POR_INDICE["ipca"])
    r["focus_ano"], r["focus_mediana"], r["focus_data"] = (
        proj if proj else (ano_atual, float("nan"), None)
    )
    return r


def calcular_ipca15():
    """
    Mesma lógica de calcular_ipca(), mas para o IPCA-15 (prévia). O BC não
    publica núcleos, quebra por durabilidade, monitorados nem difusão para
    o IPCA-15 (ver config.py) — por isso o resultado tem só geral (mês/ano/
    12m), grupos/subgrupos (IBGE/SIDRA tabela 7062) e Focus/"IPCA-15".
    """
    mensal = _serie_mensal("ipca15_geral")

    ano_atual = mensal.index.max().year
    no_ano = mensal[mensal.index.year == ano_atual]
    doze_m = _rolling_12m(mensal)
    ultimo_mes = mensal.index.max()

    r = {
        "indice": "ipca15",
        "referencia": ultimo_mes,
        "no_mes": float(mensal.iloc[-1]),
        "no_ano": float(_acumulado_composto(no_ano).iloc[-1]) if len(no_ano) else float("nan"),
        "em_12m": float(doze_m.iloc[-1]) if len(doze_m) else float("nan"),
        "meta": config.META_INFLACAO,
        "banda": config.META_TOLERANCIA,
        "serie_mensal": mensal,
        "serie_12m": doze_m,
    }
    r["desvio_meta"] = r["em_12m"] - config.META_INFLACAO
    r["dentro_banda"] = abs(r["desvio_meta"]) <= config.META_TOLERANCIA

    r.update(movimentos_ibge(indice="ipca15"))

    proj = focus.projecao_ano_corrente(indicador=config.FOCUS_INDICADOR_POR_INDICE["ipca15"])
    r["focus_ano"], r["focus_mediana"], r["focus_data"] = (
        proj if proj else (ano_atual, float("nan"), None)
    )
    return r


def persistir(r):
    """Grava os indicadores calculados em `indicadores`, prefixados pelo
    índice (r["indice"]: 'ipca' ou 'ipca15') para não colidir entre si."""
    prefixo = r.get("indice", "ipca")
    ref = r["referencia"].strftime("%Y-%m-%d")
    linhas = [
        (f"{prefixo}_no_mes", ref, r["no_mes"]),
        (f"{prefixo}_no_ano", ref, r["no_ano"]),
        (f"{prefixo}_12m", ref, r["em_12m"]),
        (f"{prefixo}_desvio_meta", ref, r["desvio_meta"]),
        (f"focus_mediana_ano_corrente_{prefixo}", ref, r["focus_mediana"]),
    ]
    for chave in ("mm3_anualizada", "servicos_12m", "nucleos_12m", "difusao"):
        if chave in r:
            linhas.append((f"{prefixo}_{chave}", ref, r[chave]))
    db.salvar_indicadores(linhas)
    log.info("Indicadores (%s) persistidos (referência %s).", prefixo, ref)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = calcular_ipca()
    persistir(r)
    print(f"IPCA {r['referencia']:%b/%Y}: {r['no_mes']:.2f}% mês | {r['no_ano']:.2f}% ano | "
          f"{r['em_12m']:.2f}% 12m | serviços {r['servicos_12m']:.2f}% | "
          f"núcleos {r['nucleos_12m']:.2f}% | difusão {r['difusao']:.1f}% | "
          f"Focus {r['focus_ano']}: {r['focus_mediana']:.2f}%")
