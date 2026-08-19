"""
orquestrador.py — O MAESTRO.

Encadeia os quatro robôs: coleta -> tratamento -> modelagem -> relatório.
Cada etapa "passa a bola" para a próxima. Se uma falha, o erro é registrado
com contexto suficiente para diagnóstico (ou para o agente se autocorrigir).

Uso:
    python orquestrador.py                        # produção, IPCA, 1ª edição
    python orquestrador.py --offline               # demonstração com dados sintéticos
    python orquestrador.py --indice=ipca15          # boletim do IPCA-15 (sem núcleo)
    python orquestrador.py --edicao=2               # 2ª edição do dia (núcleo atualizado)

`--edicao` só afeta o IPCA cheio (título do e-mail e cabeçalho do PDF); o
IPCA-15 tem edição única. `--indice` aceita "ipca" (padrão) ou "ipca15".

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


def executar(offline=False, indice="ipca", edicao=1):
    log = logging.getLogger("orquestrador")
    inicio = datetime.now()
    log.info("=== Pipeline iniciado (offline=%s, indice=%s, edicao=%s) ===",
              offline, indice, edicao)

    try:
        if indice == "ipca15":
            # ROBÔ 1 — coleta (SGS do IPCA-15 + Focus "IPCA-15" + peso IBGE/SIDRA tabela 7062)
            n = coleta.coletar(offline=offline, series=config.SERIES_IPCA15)
            focus.coletar(offline=offline, indicador=config.FOCUS_INDICADOR_POR_INDICE["ipca15"])
            ibge.coletar(offline=offline, indice="ipca15")
            log.info("[1/4] Coleta (IPCA-15): %d observações + expectativas Focus + peso IBGE.", n)

            # ROBÔS 2+3 — modelagem sem núcleo/serviços/monitorados/difusão
            resultado = modelagem.calcular_ipca15()
        else:
            # ROBÔ 1 — coleta (SGS realizados + Focus/Olinda + peso IBGE/SIDRA)
            n = coleta.coletar(offline=offline)
            focus.coletar(offline=offline)
            ibge.coletar(offline=offline)
            log.info("[1/4] Coleta: %d observações + expectativas Focus + peso IBGE.", n)

            # ROBÔS 2+3 — tratamento e modelagem (o cálculo já chama o tratamento)
            resultado = modelagem.calcular_ipca()

        modelagem.persistir(resultado)
        log.info("[2-3/4] Modelagem: %s 12m = %.2f%%.", indice.upper(), resultado["em_12m"])

        # ROBÔ 4 — relatório (PDF com gráficos, .txt e .html para e-mail)
        pdf = relatorio.gerar_pdf(resultado, edicao=edicao)
        texto = relatorio.gerar_texto(resultado, edicao=edicao)
        html = relatorio.gerar_html(resultado, edicao=edicao)
        log.info("[4/4] Relatório: %s (+ %s, %s)", pdf, texto, html)

        dur = (datetime.now() - inicio).total_seconds()
        log.info("=== Pipeline concluído em %.1fs ===", dur)
        return pdf

    except Exception as e:
        # Erro com contexto: é isto que você cola no Claude (ou o agente lê
        # do log) para o padrão de autocorreção funcionar.
        log.exception("Pipeline interrompido: %s", e)
        raise


def _parse_args(argv):
    offline = "--offline" in argv
    indice = "ipca"
    edicao = 1
    for arg in argv:
        if arg.startswith("--indice="):
            indice = arg.split("=", 1)[1]
        elif arg.startswith("--edicao="):
            edicao = int(arg.split("=", 1)[1])
    if indice not in ("ipca", "ipca15"):
        raise ValueError(f"--indice inválido: {indice!r} (use 'ipca' ou 'ipca15')")
    return offline, indice, edicao


if __name__ == "__main__":
    configurar_log()
    _offline, _indice, _edicao = _parse_args(sys.argv[1:])
    executar(offline=_offline, indice=_indice, edicao=_edicao)
