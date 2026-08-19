"""
orquestrador.py — O MAESTRO.

Encadeia os quatro robôs: coleta -> tratamento -> modelagem -> relatório.
Cada etapa "passa a bola" para a próxima. Se uma falha, o erro é registrado
com contexto suficiente para diagnóstico (ou para o agente se autocorrigir).

Uso:
    python orquestrador.py                # produção (bate na API do BC)
    python orquestrador.py --offline      # demonstração com dados sintéticos

Este é o arquivo que você agenda (cron, Task Scheduler, GitHub Actions)
para rodar toda manhã.
"""

import sys
import logging
from datetime import datetime

import config
import coleta
import focus
import ibge
import modelagem
import relatorio


def configurar_log():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def executar(offline=False):
    log = logging.getLogger("orquestrador")
    inicio = datetime.now()
    log.info("=== Pipeline iniciado (offline=%s) ===", offline)

    try:
        # ROBÔ 1 — coleta (SGS realizados + Focus/Olinda + peso IBGE/SIDRA)
        n = coleta.coletar(offline=offline)
        focus.coletar(offline=offline)
        ibge.coletar(offline=offline)
        log.info("[1/4] Coleta: %d observações + expectativas Focus + peso IBGE.", n)

        # ROBÔS 2+3 — tratamento e modelagem (o cálculo já chama o tratamento)
        resultado = modelagem.calcular_ipca()
        modelagem.persistir(resultado)
        log.info("[2-3/4] Modelagem: IPCA 12m = %.2f%%.", resultado["em_12m"])

        # ROBÔ 4 — relatório
        pdf = relatorio.gerar_pdf(resultado)
        log.info("[4/4] Relatório: %s", pdf)

        dur = (datetime.now() - inicio).total_seconds()
        log.info("=== Pipeline concluído em %.1fs ===", dur)
        return pdf

    except Exception as e:
        # Erro com contexto: é isto que você cola no Claude (ou o agente lê
        # do log) para o padrão de autocorreção funcionar.
        log.exception("Pipeline interrompido: %s", e)
        raise


if __name__ == "__main__":
    configurar_log()
    executar(offline="--offline" in sys.argv)
