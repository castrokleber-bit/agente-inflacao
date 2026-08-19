# Contexto do projeto — Agente de Inflação (GPE)

> Este arquivo é lido automaticamente pelo Claude Code / Claude Desktop toda
> vez que ele abre este diretório. É a "memória permanente" do agente: em vez
> de você reexplicar o projeto a cada sessão, as regras ficam aqui. **Mantenha
> curto e factual.**

## O que este projeto faz
Pipeline autônomo que coleta indicadores de inflação do Banco Central — séries
realizadas do SGS e a mediana do Focus (API Olinda) — armazena em SQLite,
calcula variações e recortes (serviços, núcleos, difusão) e gera relatório em
PDF. Módulos de responsabilidade única, encadeados pelo `orquestrador.py`:
`coleta.py` (SGS) → `tratamento.py` (limpeza) → `modelagem.py` (cálculo) →
`relatorio.py` (PDF), com `focus.py` alimentando a projeção. Tudo passa pelo
SQLite (`dados/macro.db`), que também é lido pelo Claude via MCP.
Recortes acompanhados: IPCA geral, serviços, quebra por durabilidade,
monitorados, núcleos (MS/EX0/DP/EX3/P55) e difusão. Projeção = mediana do Focus.

## Regras de trabalho (obedeça sempre)
- **Fonte primária é o SGS do Banco Central.** Nunca invente números; se um
  dado não está no `dados/macro.db`, rode a coleta antes de responder.
- Código e comentários em **português (pt-BR)**.
- Séries e códigos SGS vivem em `config.py`. Para adicionar um indicador,
  edite só o dicionário `SERIES` — não espalhe códigos pelo código.
- Datas internas sempre em ISO (`AAAA-MM-DD`). O SGS entrega em pt-BR; a
  conversão é feita na coleta.
- Toda projeção deve vir rotulada como estimativa e com a metodologia. Nunca
  apresente a projeção ingênua como "previsão do agente".
- Ao mexer em qualquer robô, mantenha a **responsabilidade única** de cada
  arquivo (coleta não calcula; modelagem não formata PDF).

## Como calcular (definições canônicas)
- **Acumulado no ano / 12 meses:** composição de variações mensais
  `((1 + v/100).prod() - 1) * 100` — nunca soma simples.
- **Média dos núcleos:** média em 12m dos núcleos em `config.NUCLEOS` — conjunto
  oficial do BC: MS (4466), EX0 (11427), DP (16122), EX3 (27839) e P55 (28750).
- **Difusão:** nível (0–100%), não se acumula; é % de subitens em alta.
- **Projeção do IPCA geral:** mediana do Focus (`focus.py`), recurso Olinda
  `ExpectativasMercadoAnuais`, `baseCalculo=0`. Nunca substitua por chute.
- **Meta vigente:** ver `META_INFLACAO`/`META_TOLERANCIA` em `config.py`.
  Regime de meta contínua (3,0% ± 1,5 p.p.); confirme antes de afirmar.

## Pendência conhecida
- **Bens industriais (livres):** investigado em 2026-08-19 — **não existe**
  como série própria no SGS do Banco Central (busca exaustiva no catálogo do
  Portal de Dados Abertos, que espelha o localizador do SGS). O SGS só tem o
  agregado de "livres" (11428) e a quebra por durabilidade (10841-10844,
  já em `SERIES`). A tríade alimentação no domicílio/industriais/serviços é
  classificação do IBGE (SIDRA), não do BC. Não invente um código SGS para
  isso — se o recorte for necessário, colete via API SIDRA do IBGE. Ver
  comentário detalhado em `config.py` acima de `SERIES_A_CONFIRMAR`.

## Comandos úteis
- `python orquestrador.py` — pipeline completo (produção).
- `python orquestrador.py --offline` — demonstração sem internet.
- `python modelagem.py` — recalcula e imprime os números-chave.
- Cada robô roda isolado (não há suíte de testes; o bloco `if __name__` de
  cada arquivo é o smoke test): `python coleta.py --offline`,
  `python focus.py --offline`, `python tratamento.py`, `python relatorio.py`.

## Banco de dados (para consultas via MCP)
Arquivo: `dados/macro.db`
- `observacoes(serie, data, valor)` — dados brutos, formato longo.
- `indicadores(nome, data, valor)` — indicadores já calculados.
- `series_meta(serie, codigo_sgs, descricao, atualizado_em)` — catálogo.
- `focus_ipca(data_coleta, ano_referencia, mediana, media, minimo, maximo)` —
  expectativas do Focus por ano de referência e data de divulgação.

Ao responder perguntas sobre os dados, **escreva SQL contra estas tabelas**
em vez de recalcular na memória.
