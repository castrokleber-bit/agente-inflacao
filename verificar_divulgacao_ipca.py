"""
verificar_divulgacao_ipca.py — checa se HOJE é uma data oficial de
divulgação do IPCA (ou do IPCA-15), segundo o calendário de indicadores
do IBGE.

As datas de divulgação não seguem um padrão fixo de cron: o IPCA cheio sai
entre os dias ~5 e ~13 do mês; o IPCA-15 sai numa janela bem distinta,
~19 a ~28 (confirmado consultando o calendário do IBGE e filtrando pelo
produto "Índice Nacional de Preços ao Consumidor Amplo 15"). Em vez de
tentar acertar o dia exato no agendamento, o workflow roda todo dia na
janela correspondente e usa este script para decidir se é para valer ou
não.

Uso:
    python verificar_divulgacao_ipca.py                # checa o IPCA cheio
    python verificar_divulgacao_ipca.py --indice=ipca15 # checa o IPCA-15

Sai com código 0 se hoje é dia de divulgação; código 1 caso contrário
(inclusive em caso de erro de rede — não bloqueia o workflow).
"""

import sys
from datetime import datetime

import requests

import config

IBGE_CALENDARIO_URL = "https://servicodados.ibge.gov.br/api/v3/calendario"


def hoje_e_dia_de_divulgacao(indice="ipca"):
    produto_id = config.IBGE_CALENDARIO_PRODUTO[indice]
    resp = requests.get(IBGE_CALENDARIO_URL, timeout=30)
    resp.raise_for_status()
    hoje = datetime.now().date()
    for item in resp.json().get("items", []):
        if item.get("produto_id") != produto_id:
            continue
        data = datetime.strptime(item["data_divulgacao"], "%d/%m/%Y %H:%M:%S").date()
        if data == hoje:
            return True
    return False


if __name__ == "__main__":
    indice = "ipca15" if "--indice=ipca15" in sys.argv else "ipca"
    rotulo = "IPCA-15" if indice == "ipca15" else "IPCA"

    try:
        divulgacao_hoje = hoje_e_dia_de_divulgacao(indice)
    except Exception as e:  # noqa: BLE001 — falha de rede não deve travar o workflow
        print(f"Falha ao consultar o calendário do IBGE ({rotulo}): {e}")
        sys.exit(1)

    if divulgacao_hoje:
        print(f"Hoje é dia de divulgação do {rotulo}.")
        sys.exit(0)

    print(f"Hoje não é dia de divulgação do {rotulo} — nada a fazer.")
    sys.exit(1)
