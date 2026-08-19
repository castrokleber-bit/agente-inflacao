"""
config.py — Parâmetros centrais do Agente de Inflação.

Tudo que muda de instituição para instituição (ou que você quer versionar
sem mexer na lógica) fica aqui. É o primeiro lugar que um agente de IA lê
para entender "as regras do jogo".
"""

from pathlib import Path

# --- Caminhos ---------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "dados" / "macro.db"          # SQLite lido pelo MCP
OUTPUT_DIR = BASE_DIR / "saidas"                    # PDFs e gráficos
LOG_PATH = BASE_DIR / "execucao.log"

# --- Fonte 1: Banco Central / SGS (séries realizadas) -----------------------
# Endpoint confirmado:
#   https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json
# Retorno: [{"data": "01/06/2025", "valor": "0.24"}, ...]
SGS_BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"

# Séries coletadas. Chave = nome interno; valor = (código SGS, descrição).
# TODOS os códigos abaixo foram conferidos na documentação oficial do SGS.
SERIES = {
    # --- IPCA cheio e acumulados ---
    "ipca_geral":        (433,   "IPCA geral - variação mensal (%)"),
    "ipca_12m":          (13522, "IPCA geral - acumulado em 12 meses (%)"),
    # --- Aberturas por natureza do bem/serviço ---
    "ipca_servicos":     (10844, "IPCA - Serviços - variação mensal (%)"),
    "ipca_duraveis":     (10843, "IPCA - Bens duráveis - variação mensal (%)"),
    "ipca_semiduraveis": (10842, "IPCA - Bens semiduráveis - variação mensal (%)"),
    "ipca_naoduraveis":  (10841, "IPCA - Bens não-duráveis - variação mensal (%)"),
    "ipca_monitorados":  (4449,  "IPCA - Preços monitorados - variação mensal (%)"),
    # --- Núcleos (medidas subjacentes) — conjunto oficial da "média dos núcleos" ---
    "ipca_nucleo_ms":    (4466,  "Núcleo IPCA - médias aparadas COM suavização (MS)"),
    "ipca_nucleo_ex0":   (11427, "Núcleo IPCA - por exclusão EX0"),
    "ipca_nucleo_dp":    (16122, "Núcleo IPCA - dupla ponderação (DP)"),
    "ipca_nucleo_ex3":   (27839, "Núcleo IPCA - por exclusão EX3"),
    "ipca_nucleo_p55":   (28750, "Núcleo IPCA - percentil 55 (P55)"),
    # --- Difusão ---
    "ipca_difusao":      (21379, "IPCA - índice de difusão (% de subitens em alta)"),
    # --- Contexto macro ---
    "selic_meta":        (432,   "Selic - meta definida pelo Copom (% a.a.)"),
    "cambio_venda":      (1,     "Câmbio USD/BRL - venda (diário)"),
}

# --- Fonte 3: IBGE / SIDRA (peso e variação por grupo e subgrupo do IPCA) ---
# O SGS do Banco Central não publica peso (participação na cesta) por grupo
# — só o IBGE, que calcula o índice, tem essa informação. Usamos a tabela
# 7060 do SIDRA (variação mensal, acumulada em 12m e peso mensal, por
# grupo/subgrupo/item/subitem, desde jan/2020) para calcular a contribuição
# em pontos percentuais (peso/100 * variação) e apontar quem de fato "puxou"
# o IPCA no mês — bem mais informativo que comparar variações brutas de
# grupos com pesos muito diferentes. Guardamos só os níveis grupo e subgrupo.
# Endpoint confirmado (validado com os 9 grupos batendo 100% de peso, e a
# soma peso*variação reconstruindo a variação mensal do índice geral):
#   https://apisidra.ibge.gov.br/values/t/7060/n1/1/v/63,66,2265/p/last%201/
#   c315/{códigos}?formato=json
IBGE_SIDRA_BASE_URL = (
    "https://apisidra.ibge.gov.br/values/t/7060/n1/1/v/{variaveis}/p/last%201/c315/{codigos}"
)
IBGE_SIDRA_VARIAVEIS = "63,66,2265"  # variação mensal, peso mensal, variação 12 meses

# Grupos (nível 1) do IPCA — código SIDRA: (grupo_numero, nome).
IBGE_GRUPOS = {
    7170: (1, "Alimentação e bebidas"),
    7445: (2, "Habitação"),
    7486: (3, "Artigos de residência"),
    7558: (4, "Vestuário"),
    7625: (5, "Transportes"),
    7660: (6, "Saúde e cuidados pessoais"),
    7712: (7, "Despesas pessoais"),
    7766: (8, "Educação"),
    7786: (9, "Comunicação"),
}

# Subgrupos (nível 2) do IPCA — código SIDRA: (grupo_numero pai, nome).
IBGE_SUBGRUPOS = {
    7171:  (1, "Alimentação no domicílio"),
    7432:  (1, "Alimentação fora do domicílio"),
    7446:  (2, "Encargos e manutenção"),
    7479:  (2, "Combustíveis e energia"),
    7487:  (3, "Móveis e utensílios"),
    7521:  (3, "Aparelhos eletroeletrônicos"),
    7548:  (3, "Consertos e manutenção"),
    7559:  (4, "Roupas"),
    7604:  (4, "Calçados e acessórios"),
    7615:  (4, "Joias e bijuterias"),
    7620:  (4, "Tecidos e armarinho"),
    7626:  (5, "Transportes"),
    7661:  (6, "Produtos farmacêuticos e óticos"),
    7683:  (6, "Serviços de saúde"),
    7697:  (6, "Cuidados pessoais"),
    7713:  (7, "Serviços pessoais"),
    47656: (7, "Recreação e fumo"),
    7767:  (8, "Cursos, leitura e papelaria"),
    7787:  (9, "Comunicação"),
}

# Conjunto de séries cujo código eu NÃO confirmei com 100% de certeza.
#
# INVESTIGAÇÃO (2026-08-19): "IPCA - Livres - Bens industriais" NÃO existe
# como série própria no SGS do Banco Central. Busquei no catálogo completo
# do Portal de Dados Abertos do BC (que espelha o localizador do SGS) por
# "bens industriais", "industriais", "industrializados", "alimentação no
# domicílio"/"domicilio" e variantes — nenhum resultado. O que o BC de fato
# publica no SGS para o grupo "livres" é só o agregado:
#   - 11428: IPCA - Itens livres (agregado, sem quebra por Alimentação no
#     domicílio / Industriais / Serviços)
#   - 4447/4448: IPCA - Comercializáveis / Não comercializáveis (outro corte)
#   - 10841-10844: quebra por durabilidade (já em SERIES)
# A tríade "Alimentação no domicílio / Industriais / Serviços" dentro de
# "livres" é classificação do IBGE (tabela SIDRA), não republicada pelo BC
# como série SGS individual. Não invente um código — se precisar desse
# recorte, colete via API SIDRA do IBGE (ver README) em vez de forçar isso
# no SGS.
SERIES_A_CONFIRMAR = {
    # "ipca_bens_industriais": (CODIGO_A_CONFIRMAR, "IPCA - Livres - Bens industriais (%)"),
}

# Média dos núcleos (conjunto oficial do BC): MS, EX0, DP, EX3 e P55.
NUCLEOS = ["ipca_nucleo_ms", "ipca_nucleo_ex0", "ipca_nucleo_dp",
           "ipca_nucleo_ex3", "ipca_nucleo_p55"]

# Quantos anos de histórico buscar na primeira carga.
HISTORICO_ANOS = 6

# --- Fonte 2: Olinda / Expectativas de Mercado (Focus) ----------------------
# Projeção de IPCA = mediana das expectativas anuais do Focus (baseCalculo 0).
# Endpoint confirmado:
FOCUS_BASE_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
    "{recurso}"
)
FOCUS_RECURSO_ANUAL = "ExpectativasMercadoAnuais"
FOCUS_INDICADOR = "IPCA"
FOCUS_BASE_CALCULO = 0        # 0 = expectativa do dia; 1 = média dos últimos 5 dias úteis
FOCUS_ANOS_PROJECAO = 3       # ano corrente + 2 seguintes

# --- Regra de meta de inflação (regime de meta contínua, a partir de 2025) --
META_INFLACAO = 3.0          # centro da meta (%)
META_TOLERANCIA = 1.5        # banda (± p.p.)

# --- Rótulo institucional (cabeçalho do relatório) --------------------------
INSTITUICAO = "GPE — Gerência Executiva de Política Econômica"
AUTOR_RELATORIO = "Agente de Inflação (automatizado)"

# --- Robustez de rede -------------------------------------------------------
HTTP_TIMEOUT = 30
HTTP_TENTATIVAS = 3
HTTP_BACKOFF = 2.0
