"""
baixar_copa_2026.py
====================
Baixa os dados da Copa do Mundo 2026 da API football-data.org (v4) e salva em CSVs
prontos pra análise no pandas.

O que ele gera (todos ligados pela coluna match_id):
    - partidas.csv          -> 1 linha por jogo (placar, fase, grupo, times, etc.)
    - gols.csv              -> 1 linha por gol (quem fez, minuto, tipo, assistência)
    - cartoes.csv           -> 1 linha por cartão (jogador, minuto, cor)
    - substituicoes.csv     -> 1 linha por substituição (entrou/saiu, minuto)
    - escalacoes.csv        -> 1 linha por jogador escalado (titular/banco, posição)
    - estatisticas_time.csv -> 1 linha por time/jogo (posse, chutes, faltas, etc.)

----------------------------------------------------------------------
COMO USAR
----------------------------------------------------------------------
1. Crie uma conta gratuita e pegue seu token em:
       https://www.football-data.org/client/register
   (chega por e-mail; é uma string tipo "abc123def456...")

2. Instale as dependências:
       pip install requests pandas

3. Rode passando o token. Duas formas:
       export FOOTBALL_DATA_TOKEN="seu_token_aqui"
       python baixar_copa_2026.py
   ou direto:
       python baixar_copa_2026.py --token seu_token_aqui

----------------------------------------------------------------------
ATENÇÃO — leia antes de rodar
----------------------------------------------------------------------
* A Copa do Mundo (código WC, id 2000) NEM SEMPRE está liberada no plano
  gratuito. Se você tomar um erro 403 (Forbidden), é isso: a competição não
  está no seu tier. O script avisa de forma clara quando isso acontece.

* Detalhes ricos (gols, cartões, subs, escalações) só vêm no endpoint de
  partida individual (/matches/{id}). Por isso o script faz 1 request por
  jogo. Numa Copa de 104 jogos, a 10 req/min, são uns ~11 minutos. O script
  respeita o rate limit automaticamente (pausa e tenta de novo no 429).

* Jogos que ainda não foram disputados vêm com status SCHEDULED/TIMED e
  SEM placar/eventos. Isso é normal — o CSV registra esses jogos do mesmo
  jeito, só com os campos de resultado vazios.
"""

import argparse
import csv
import os
import sys
import time

import requests
import pandas as pd

# ----------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------
BASE_URL = "https://api.football-data.org/v4"
COMPETICAO = "WC"          # código da FIFA World Cup (id 2000)
TEMPORADA = 2026           # ano de início da temporada da Copa
PASTA_SAIDA = "dados_copa_2026"

# No plano gratuito o limite é 10 req/min. Deixamos uma folga de segurança
# esperando ~6.5s entre requests pra nunca encostar no teto.
PAUSA_ENTRE_REQUESTS = 6.5  # segundos


# ----------------------------------------------------------------------
# Camada de request: 1 função central que lida com auth, rate limit e erros
# ----------------------------------------------------------------------
def buscar(endpoint, token, params=None, unfold=False):
    """
    Faz um GET na API e devolve o JSON.

    Se unfold=True, pede pra API "desdobrar" gols/cartões/subs/escalações
    (necessário no endpoint de partida individual).

    Trata o rate limit (HTTP 429) automaticamente: lê o header que diz
    quantos segundos faltam pra resetar o contador e espera esse tempo.
    """
    url = f"{BASE_URL}/{endpoint}"
    headers = {"X-Auth-Token": token}
    if unfold:
        headers.update({
            "X-Unfold-Goals": "true",
            "X-Unfold-Bookings": "true",
            "X-Unfold-Subs": "true",
            "X-Unfold-Lineups": "true",
        })

    # Tenta até 5 vezes em caso de rate limit
    for tentativa in range(5):
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 429:
            # Rate limit estourado. O header diz quantos segundos faltam.
            espera = int(resp.headers.get("X-RequestCounter-Reset", 60)) + 1
            print(f"   [rate limit] aguardando {espera}s antes de tentar de novo...")
            time.sleep(espera)
            continue

        if resp.status_code == 403:
            raise PermissionError(
                "403 Forbidden — a Copa do Mundo (WC) provavelmente NÃO está "
                "liberada no seu plano gratuito. Confira em football-data.org "
                "quais competições seu token cobre, ou peça upgrade do tier."
            )

        if resp.status_code == 401:
            raise PermissionError(
                "401 Unauthorized — token inválido ou ausente. Confira sua chave."
            )

        # Qualquer outro erro: mostra e levanta
        resp.raise_for_status()

    raise RuntimeError("Excedido o número de tentativas por causa do rate limit.")


# ----------------------------------------------------------------------
# Helpers de extração — transformam o JSON aninhado em linhas planas (flat)
# ----------------------------------------------------------------------
def _safe(d, *chaves):
    """Acessa d[chave1][chave2]... devolvendo None se qualquer nível faltar."""
    for c in chaves:
        if d is None:
            return None
        d = d.get(c) if isinstance(d, dict) else None
    return d


def extrair_partida(m):
    """Uma partida -> 1 dict plano com o resultado e metadados do jogo."""
    return {
        "match_id": m.get("id"),
        "utc_date": m.get("utcDate"),
        "status": m.get("status"),
        "stage": m.get("stage"),            # GROUP_STAGE, LAST_16, FINAL, etc.
        "group": m.get("group"),            # GROUP_A ... ou None nos mata-mata
        "matchday": m.get("matchday"),
        "venue": m.get("venue"),
        "attendance": m.get("attendance"),
        "home_team_id": _safe(m, "homeTeam", "id"),
        "home_team": _safe(m, "homeTeam", "name"),
        "away_team_id": _safe(m, "awayTeam", "id"),
        "away_team": _safe(m, "awayTeam", "name"),
        "home_coach": _safe(m, "homeTeam", "coach", "name"),
        "away_coach": _safe(m, "awayTeam", "coach", "name"),
        "home_formation": _safe(m, "homeTeam", "formation"),
        "away_formation": _safe(m, "awayTeam", "formation"),
        "winner": _safe(m, "score", "winner"),          # HOME_TEAM / AWAY_TEAM / DRAW
        "duration": _safe(m, "score", "duration"),      # REGULAR / EXTRA_TIME / PENALTY_SHOOTOUT
        "fulltime_home": _safe(m, "score", "fullTime", "home"),
        "fulltime_away": _safe(m, "score", "fullTime", "away"),
        "halftime_home": _safe(m, "score", "halfTime", "home"),
        "halftime_away": _safe(m, "score", "halfTime", "away"),
        "referee": next(
            (r.get("name") for r in (m.get("referees") or [])
             if r.get("type") == "REFEREE"),
            None,
        ),
    }


def extrair_gols(m):
    """Uma partida -> várias linhas, uma por gol."""
    linhas = []
    for g in (m.get("goals") or []):
        linhas.append({
            "match_id": m.get("id"),
            "minute": g.get("minute"),
            "injury_time": g.get("injuryTime"),
            "type": g.get("type"),                       # REGULAR / OWN / PENALTY
            "team_id": _safe(g, "team", "id"),
            "team": _safe(g, "team", "name"),
            "scorer_id": _safe(g, "scorer", "id"),
            "scorer": _safe(g, "scorer", "name"),
            "assist_id": _safe(g, "assist", "id"),
            "assist": _safe(g, "assist", "name"),
            "score_home": _safe(g, "score", "home"),
            "score_away": _safe(g, "score", "away"),
        })
    return linhas


def extrair_cartoes(m):
    """Uma partida -> várias linhas, uma por cartão."""
    linhas = []
    for b in (m.get("bookings") or []):
        linhas.append({
            "match_id": m.get("id"),
            "minute": b.get("minute"),
            "team_id": _safe(b, "team", "id"),
            "team": _safe(b, "team", "name"),
            "player_id": _safe(b, "player", "id"),
            "player": _safe(b, "player", "name"),
            "card": b.get("card"),                       # YELLOW / YELLOW_RED / RED
        })
    return linhas


def extrair_substituicoes(m):
    """Uma partida -> várias linhas, uma por substituição."""
    linhas = []
    for s in (m.get("substitutions") or []):
        linhas.append({
            "match_id": m.get("id"),
            "minute": s.get("minute"),
            "team_id": _safe(s, "team", "id"),
            "team": _safe(s, "team", "name"),
            "player_out_id": _safe(s, "playerOut", "id"),
            "player_out": _safe(s, "playerOut", "name"),
            "player_in_id": _safe(s, "playerIn", "id"),
            "player_in": _safe(s, "playerIn", "name"),
        })
    return linhas


def extrair_escalacoes(m):
    """Uma partida -> várias linhas, uma por jogador (titular + banco, dos 2 times)."""
    linhas = []
    for lado in ("homeTeam", "awayTeam"):
        time_ = m.get(lado) or {}
        for tipo, chave in (("STARTING", "lineup"), ("BENCH", "bench")):
            for jog in (time_.get(chave) or []):
                linhas.append({
                    "match_id": m.get("id"),
                    "team_id": time_.get("id"),
                    "team": time_.get("name"),
                    "side": "home" if lado == "homeTeam" else "away",
                    "role": tipo,                        # STARTING / BENCH
                    "player_id": jog.get("id"),
                    "player": jog.get("name"),
                    "position": jog.get("position"),
                    "shirt_number": jog.get("shirtNumber"),
                })
    return linhas


def extrair_estatisticas(m):
    """Uma partida -> até 2 linhas (uma por time) com as estatísticas agregadas."""
    linhas = []
    for lado in ("homeTeam", "awayTeam"):
        time_ = m.get(lado) or {}
        stats = time_.get("statistics")
        if not stats:
            continue
        linha = {
            "match_id": m.get("id"),
            "team_id": time_.get("id"),
            "team": time_.get("name"),
            "side": "home" if lado == "homeTeam" else "away",
        }
        linha.update(stats)  # corner_kicks, ball_possession, shots, etc.
        linhas.append(linha)
    return linhas


# ----------------------------------------------------------------------
# Fluxo principal
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Baixa dados da Copa 2026.")
    parser.add_argument("--token", help="Token da football-data.org "
                        "(ou use a variável de ambiente FOOTBALL_DATA_TOKEN).")
    parser.add_argument("--season", type=int, default=TEMPORADA,
                        help=f"Ano da temporada (padrão: {TEMPORADA}).")
    parser.add_argument("--saida", default=PASTA_SAIDA,
                        help=f"Pasta de saída (padrão: {PASTA_SAIDA}).")
    args = parser.parse_args()

    token = args.token or os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        sys.exit("ERRO: nenhum token informado. Use --token ou defina "
                 "FOOTBALL_DATA_TOKEN. Pegue o seu em "
                 "https://www.football-data.org/client/register")

    os.makedirs(args.saida, exist_ok=True)

    # --- Passo 1: listar todas as partidas da Copa nessa temporada ----------
    print(f"Buscando lista de partidas da Copa {args.season}...")
    try:
        lista = buscar(
            f"competitions/{COMPETICAO}/matches",
            token,
            params={"season": args.season},
        )
    except PermissionError as e:
        sys.exit(f"\nERRO DE ACESSO:\n{e}")

    partidas = lista.get("matches", [])
    total = len(partidas)
    if total == 0:
        sys.exit("Nenhuma partida retornada. A temporada pode ainda não estar "
                 "cadastrada na API, ou o filtro de season não bateu.")

    print(f"-> {total} partidas encontradas. Buscando detalhes de cada uma...")
    print(f"   (a ~{PAUSA_ENTRE_REQUESTS}s por jogo, isso leva uns "
          f"{total * PAUSA_ENTRE_REQUESTS / 60:.0f} minutos)\n")

    # Acumuladores
    rows_partidas, rows_gols, rows_cartoes = [], [], []
    rows_subs, rows_escala, rows_stats = [], [], []

    # --- Passo 2: para cada partida, buscar o detalhe completo --------------
    for i, p in enumerate(partidas, 1):
        match_id = p.get("id")
        print(f"[{i}/{total}] partida {match_id} "
              f"({_safe(p, 'homeTeam', 'name')} x {_safe(p, 'awayTeam', 'name')})")

        try:
            m = buscar(f"matches/{match_id}", token, unfold=True)
        except Exception as e:
            # Se um jogo falhar, registra o resultado básico e segue
            print(f"   aviso: não consegui o detalhe ({e}). Uso o resumo da lista.")
            m = p

        rows_partidas.append(extrair_partida(m))
        rows_gols.extend(extrair_gols(m))
        rows_cartoes.extend(extrair_cartoes(m))
        rows_subs.extend(extrair_substituicoes(m))
        rows_escala.extend(extrair_escalacoes(m))
        rows_stats.extend(extrair_estatisticas(m))

        # Respeita o rate limit (não pausa depois do último)
        if i < total:
            time.sleep(PAUSA_ENTRE_REQUESTS)

    # --- Passo 3: montar DataFrames e salvar CSVs ---------------------------
    print("\nSalvando CSVs...")
    saidas = {
        "partidas.csv": rows_partidas,
        "gols.csv": rows_gols,
        "cartoes.csv": rows_cartoes,
        "substituicoes.csv": rows_subs,
        "escalacoes.csv": rows_escala,
        "estatisticas_time.csv": rows_stats,
    }
    for nome, rows in saidas.items():
        caminho = os.path.join(args.saida, nome)
        df = pd.DataFrame(rows)
        # utf-8-sig pra abrir bonito no Excel também, sem quebrar acentos
        df.to_csv(caminho, index=False, encoding="utf-8-sig",
                  quoting=csv.QUOTE_MINIMAL)
        print(f"   {caminho:45s} {len(df):4d} linhas")

    print("\nPronto! Todos os arquivos ligam pela coluna match_id.")


if __name__ == "__main__":
    main()
