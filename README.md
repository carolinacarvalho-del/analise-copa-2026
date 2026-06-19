# Análise de Dados — Copa do Mundo 2026

Repositório com o script de download e o notebook de análise dos dados da Copa do Mundo 2026, usando Python e Pandas.

## O que tem aqui

- `baixar_copa_2026.py` — script que conecta na API pública da [football-data.org](https://www.football-data.org), baixa os dados de todos os jogos e salva em arquivos CSV prontos pra análise
- `analise-copa-do-mundo.ipynb` — notebook com a análise completa da rodada 1: gols por seleção, saldo dos lanternas, desempenho por confederação e muito mais

## Como usar

### 1. Crie uma conta gratuita na API

Acesse [football-data.org](https://www.football-data.org/client/register), crie uma conta e copie o token que chegará no seu e-mail.

### 2. Instale as dependências

```bash
pip install requests pandas matplotlib seaborn
```

### 3. Rode o script de download

```bash
python baixar_copa_2026.py --token seu_token_aqui
```

O script vai criar uma pasta `dados_copa_2026/` com os seguintes arquivos:

| Arquivo | Conteúdo |
|---|---|
| `partidas.csv` | 1 linha por jogo (placar, fase, grupo, times) |
| `gols.csv` | 1 linha por gol (quem fez, minuto, tipo) |
| `cartoes.csv` | 1 linha por cartão (jogador, minuto, cor) |
| `substituicoes.csv` | 1 linha por substituição |
| `escalacoes.csv` | 1 linha por jogador escalado |
| `estatisticas_time.csv` | Posse, chutes, faltas por time/jogo |

### 4. Abra o notebook

```bash
jupyter notebook analise-copa-do-mundo.ipynb
```

## Análises da rodada 1

- 🏆 Top 15 seleções com mais gols
- 📉 Saldo de gols dos lanternas de cada grupo
- 🌍 Total de gols e pontos por confederação
- 📊 Média de pontos por seleção dentro de cada confederação
- 🔍 Análise de outliers: a liderança da Europa é real?

## Sobre

Análise produzida por **Juliano Faccioni** — professor de dados e fundador da [Asimov Academy](https://asimov.academy).

Acompanhe mais conteúdos como esse no Instagram: [@prof.julianofaccioni](https://instagram.com/prof.julianofaccioni)
