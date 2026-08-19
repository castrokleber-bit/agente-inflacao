"""
verificar_divulgacao_ipca.py — checa se HOJE é uma data oficial de
divulgação do IPCA, segundo o calendário de indicadores do IBGE.

As datas de divulgação do IPCA não seguem um padrão fixo de cron (variam
entre os dias ~5 e ~13 de cada mês, ano após ano). Em vez de tentar acertar
o dia exato no agendamento, o workflow roda todo dia nessa janela e usa
este script para decidir se é para valer ou não.

Sai com código 0 se hoje é dia de divulgação do IPCA; código 1 caso
contrário (inclusive em caso de erro de rede — não bloqueia o workflow).
"""

import sys
from datetime import datetime

import requests

IBGE_CALENDARIO_URL = "https://servicodados.ibge.gov.br/api/v3/calendario"
PRODUTO_IPCA = 9256  # Índice Nacional de Preços ao Consumidor Amplo


def hoje_e_dia_de_divulgacao():
    resp = requests.get(IBGE_CALENDARIO_URL, timeout=30)
    resp.raise_for_status()
    hoje = datetime.now().date()
    for item in resp.json().get("items", []):
        if item.get("produto_id") != PRODUTO_IPCA:
            continue
        data = datetime.strptime(item["data_divulgacao"], "%d/%m/%Y %H:%M:%S").date()
        if data == hoje:
            return True
    return False


if __name__ == "__main__":
    try:
        divulgacao_hoje = hoje_e_dia_de_divulgacao()
    except Exception as e:  # noqa: BLE001 — falha de rede não deve travar o workflow
        print(f"Falha ao consultar o calendário do IBGE: {e}")
        sys.exit(1)

    if divulgacao_hoje:
        print("Hoje é dia de divulgação do IPCA.")
        sys.exit(0)

    print("Hoje não é dia de divulgação do IPCA — nada a fazer.")
    sys.exit(1)
