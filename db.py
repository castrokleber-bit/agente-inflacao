"""
db.py — Camada de persistência em SQLite.

Por que SQLite? Porque é um arquivo único, sem servidor, e o Model Context
Protocol (MCP) tem um servidor pronto que expõe esse arquivo para o Claude.
Ou seja: depois que os dados estão aqui, você pergunta em português
("qual foi o IPCA de serviços nos últimos 6 meses?") e o Claude escreve o
SQL, roda e te responde — sem você abrir o banco.

Schema deliberadamente simples e "longo" (long format): uma linha por
(série, data). Isso facilita cruzamentos e é o formato que modelos de IA
leem melhor.
"""

import sqlite3
from contextlib import contextmanager

import config


@contextmanager
def conectar():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.execute("PRAGMA journal_mode=WAL;")  # leituras concorrentes (MCP + script)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def inicializar():
    """Cria as tabelas se não existirem. Idempotente."""
    with conectar() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS series_meta (
                serie       TEXT PRIMARY KEY,
                codigo_sgs  INTEGER,
                descricao   TEXT,
                atualizado_em TEXT
            );

            CREATE TABLE IF NOT EXISTS observacoes (
                serie   TEXT NOT NULL,
                data    TEXT NOT NULL,          -- ISO: AAAA-MM-DD
                valor   REAL,
                PRIMARY KEY (serie, data)
            );

            CREATE INDEX IF NOT EXISTS idx_obs_serie ON observacoes(serie);
            CREATE INDEX IF NOT EXISTS idx_obs_data  ON observacoes(data);

            -- Tabela de indicadores calculados (saída do robô de modelagem),
            -- para o dashboard e o relatório lerem sem recomputar.
            CREATE TABLE IF NOT EXISTS indicadores (
                nome    TEXT NOT NULL,
                data    TEXT NOT NULL,
                valor   REAL,
                PRIMARY KEY (nome, data)
            );

            -- Expectativas do Focus (Olinda). Guardamos a mediana por ano de
            -- referência e a data da coleta, para acompanhar a revisão da
            -- projeção. `indicador` distingue IPCA de IPCA-15 (a Olinda
            -- publica os dois como indicadores independentes).
            CREATE TABLE IF NOT EXISTS focus_ipca (
                indicador      TEXT NOT NULL DEFAULT 'IPCA',
                data_coleta    TEXT NOT NULL,   -- quando o Focus foi divulgado
                ano_referencia INTEGER NOT NULL,
                mediana        REAL,
                media          REAL,
                minimo         REAL,
                maximo         REAL,
                PRIMARY KEY (indicador, data_coleta, ano_referencia)
            );

            -- Peso e variação por grupo/subgrupo do IPCA (IBGE/SIDRA). O SGS
            -- do BC não publica peso — só o IBGE, que calcula o índice, tem
            -- essa informação. Guardamos só o mês mais recente coletado
            -- (é uma fotografia, não uma série histórica). `indice` distingue
            -- 'ipca' (tabela SIDRA 7060) de 'ipca15' (tabela 7062) — os dois
            -- reaproveitam os MESMOS códigos de classificação SIDRA (c315),
            -- então sem essa coluna uma coleta sobrescreveria a outra.
            CREATE TABLE IF NOT EXISTS ipca_grupos (
                indice          TEXT NOT NULL DEFAULT 'ipca',
                mes             TEXT NOT NULL,  -- referência, AAAA-MM-DD
                nivel           TEXT NOT NULL,  -- 'grupo' ou 'subgrupo'
                codigo_sidra    INTEGER NOT NULL,
                grupo_numero    INTEGER NOT NULL,  -- 1-9; grupo pai do subgrupo
                nome            TEXT NOT NULL,
                variacao_mensal REAL,
                peso_mensal     REAL,
                variacao_12m    REAL,
                PRIMARY KEY (indice, mes, codigo_sidra)
            );
            """
        )
        _migrar_schema_legado(con)


def _migrar_schema_legado(con):
    """
    Bancos criados antes da distinção IPCA / IPCA-15 têm `focus_ipca` e
    `ipca_grupos` sem as colunas `indicador`/`indice` (e com PRIMARY KEY
    mais curta). SQLite não altera PK com ALTER TABLE, então recriamos a
    tabela quando a coluna nova não existe, preservando os dados como
    'IPCA'/'ipca' (o único índice que existia antes desta migração).
    """
    cols_focus = [r[1] for r in con.execute("PRAGMA table_info(focus_ipca)")]
    if cols_focus and "indicador" not in cols_focus:
        con.executescript(
            """
            ALTER TABLE focus_ipca RENAME TO focus_ipca_legado;
            CREATE TABLE focus_ipca (
                indicador      TEXT NOT NULL DEFAULT 'IPCA',
                data_coleta    TEXT NOT NULL,
                ano_referencia INTEGER NOT NULL,
                mediana        REAL,
                media          REAL,
                minimo         REAL,
                maximo         REAL,
                PRIMARY KEY (indicador, data_coleta, ano_referencia)
            );
            INSERT INTO focus_ipca
                (indicador, data_coleta, ano_referencia, mediana, media, minimo, maximo)
            SELECT 'IPCA', data_coleta, ano_referencia, mediana, media, minimo, maximo
                FROM focus_ipca_legado;
            DROP TABLE focus_ipca_legado;
            """
        )

    cols_grupos = [r[1] for r in con.execute("PRAGMA table_info(ipca_grupos)")]
    if cols_grupos and "indice" not in cols_grupos:
        con.executescript(
            """
            ALTER TABLE ipca_grupos RENAME TO ipca_grupos_legado;
            CREATE TABLE ipca_grupos (
                indice          TEXT NOT NULL DEFAULT 'ipca',
                mes             TEXT NOT NULL,
                nivel           TEXT NOT NULL,
                codigo_sidra    INTEGER NOT NULL,
                grupo_numero    INTEGER NOT NULL,
                nome            TEXT NOT NULL,
                variacao_mensal REAL,
                peso_mensal     REAL,
                variacao_12m    REAL,
                PRIMARY KEY (indice, mes, codigo_sidra)
            );
            INSERT INTO ipca_grupos
                (indice, mes, nivel, codigo_sidra, grupo_numero, nome,
                 variacao_mensal, peso_mensal, variacao_12m)
            SELECT 'ipca', mes, nivel, codigo_sidra, grupo_numero, nome,
                   variacao_mensal, peso_mensal, variacao_12m
                FROM ipca_grupos_legado;
            DROP TABLE ipca_grupos_legado;
            """
        )


def registrar_serie(serie, codigo_sgs, descricao):
    from datetime import datetime, timezone
    with conectar() as con:
        con.execute(
            """INSERT INTO series_meta (serie, codigo_sgs, descricao, atualizado_em)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(serie) DO UPDATE SET
                 codigo_sgs=excluded.codigo_sgs,
                 descricao=excluded.descricao,
                 atualizado_em=excluded.atualizado_em;""",
            (serie, codigo_sgs, descricao, datetime.now(timezone.utc).isoformat()),
        )


def salvar_observacoes(serie, registros):
    """registros: iterável de (data_iso, valor). Upsert — nunca duplica."""
    with conectar() as con:
        con.executemany(
            """INSERT INTO observacoes (serie, data, valor)
               VALUES (?, ?, ?)
               ON CONFLICT(serie, data) DO UPDATE SET valor=excluded.valor;""",
            [(serie, d, v) for d, v in registros],
        )


def salvar_indicadores(registros):
    """registros: iterável de (nome, data_iso, valor)."""
    with conectar() as con:
        con.executemany(
            """INSERT INTO indicadores (nome, data, valor)
               VALUES (?, ?, ?)
               ON CONFLICT(nome, data) DO UPDATE SET valor=excluded.valor;""",
            list(registros),
        )


def salvar_focus(registros, indicador="IPCA"):
    """registros: iterável de (data_coleta, ano_ref, mediana, media, minimo, maximo)."""
    with conectar() as con:
        con.executemany(
            """INSERT INTO focus_ipca
                 (indicador, data_coleta, ano_referencia, mediana, media, minimo, maximo)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(indicador, data_coleta, ano_referencia) DO UPDATE SET
                 mediana=excluded.mediana, media=excluded.media,
                 minimo=excluded.minimo, maximo=excluded.maximo;""",
            [(indicador, *linha) for linha in registros],
        )


def salvar_ipca_grupos(registros, indice="ipca"):
    """registros: iterável de (mes, nivel, codigo_sidra, grupo_numero, nome,
    variacao_mensal, peso_mensal, variacao_12m)."""
    with conectar() as con:
        con.executemany(
            """INSERT INTO ipca_grupos
                 (indice, mes, nivel, codigo_sidra, grupo_numero, nome,
                  variacao_mensal, peso_mensal, variacao_12m)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(indice, mes, codigo_sidra) DO UPDATE SET
                 nivel=excluded.nivel, grupo_numero=excluded.grupo_numero,
                 nome=excluded.nome, variacao_mensal=excluded.variacao_mensal,
                 peso_mensal=excluded.peso_mensal, variacao_12m=excluded.variacao_12m;""",
            [(indice, *linha) for linha in registros],
        )


def ipca_grupos_mes_mais_recente(indice="ipca"):
    """Todas as linhas (grupo + subgrupo) do mês mais recente coletado para o índice dado."""
    with conectar() as con:
        cur = con.execute(
            """SELECT mes, nivel, codigo_sidra, grupo_numero, nome,
                      variacao_mensal, peso_mensal, variacao_12m
               FROM ipca_grupos
               WHERE indice = ?
                 AND mes = (SELECT MAX(mes) FROM ipca_grupos WHERE indice = ?)
               ORDER BY nivel, grupo_numero, codigo_sidra;""",
            (indice, indice),
        )
        return cur.fetchall()


def focus_mais_recente(indicador="IPCA"):
    """(ano_referencia, mediana, data_coleta) da coleta mais recente disponível."""
    with conectar() as con:
        cur = con.execute(
            """SELECT ano_referencia, mediana, data_coleta
               FROM focus_ipca
               WHERE indicador = ?
                 AND data_coleta = (SELECT MAX(data_coleta) FROM focus_ipca WHERE indicador = ?)
               ORDER BY ano_referencia;""",
            (indicador, indicador),
        )
        return cur.fetchall()


def ler_serie(serie):
    """Retorna lista de (data_iso, valor) ordenada por data."""
    with conectar() as con:
        cur = con.execute(
            "SELECT data, valor FROM observacoes WHERE serie=? ORDER BY data;",
            (serie,),
        )
        return cur.fetchall()


def ultimo_indicador(nome):
    with conectar() as con:
        cur = con.execute(
            "SELECT data, valor FROM indicadores WHERE nome=? ORDER BY data DESC LIMIT 1;",
            (nome,),
        )
        return cur.fetchone()
