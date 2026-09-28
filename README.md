# Hevy Analytics

App pessoal de analytics para musculação. Importa todo o histórico de treinos do [Hevy](https://hevy.com) via API, mantém a base atualizada com sincronização incremental, e cruza os dados com literatura de ciência do esporte pra gerar quatro camadas de análise: **descritiva** (o que aconteceu), **diagnóstica** (por que), **preditiva** (pra onde está indo) e **prescritiva** (o que fazer a respeito) — além de rastreamento de metas com estimativa de prazo.

Sem machine learning, sem caixa-preta: todo threshold usado (volume por grupo muscular, regras de fadiga/platô, fórmulas de 1RM) fica num YAML editável, e cada insight é gerado por uma regra explícita, rastreável até o dado bruto.

## O que o app faz

- **Importação e sync incremental** — histórico completo na primeira sincronização, só o que mudou nas seguintes (endpoint `/v1/workouts/events` do Hevy), com upsert idempotente (rodar de novo nunca duplica dado).
- **1RM estimado** — Epley e Brzycki, calculado a partir das séries reais de treino.
- **Volume por grupo muscular vs. MEV/MAV/MRV** — classifica cada semana como abaixo do volume mínimo efetivo, numa faixa produtiva, ou acima do volume máximo recuperável, com crédito parcial pra músculos secundários.
- **Detecção de platô e fadiga** — RPE subindo ou reps caindo numa carga ~constante; 1RM estagnado numa janela de sessões. Ignora exercícios abandonados há mais de 90 dias (trocar de exercício não é platô).
- **"Você reage melhor a mais volume?"** — compara, por grupo muscular, se semanas de volume acima da sua própria mediana produzem mais tonnage na semana seguinte. Correlacional e exploratório (poucas semanas de dado), tratado como hipótese, não conclusão.
- **Contexto externo configurável** — atividades fora do Hevy (outro esporte, por exemplo) que podem explicar fadiga sem exigir ajuste manual toda vez.
- **Peso corporal e força relativa** — registro manual (Hevy não rastreia isso), usado pra métricas tipo "quantas vezes o peso corporal" e pra corrigir corretamente exercícios com carga adicional (ex: barra com peso, onde o Hevy loga só o peso adicionado, não o total).
- **Metas com estimativa de prazo** — peso alvo num exercício específico, múltiplo do peso corporal num grupo muscular, dobrar a carga atual, ou uma meta de redução de dor/sintoma. Cada meta reaproveita a análise de volume/responsividade pra sugerir a alavanca mais relevante, e projeta prazo por regressão linear simples sobre a tendência recente.
- **Resumo na Home** — pontos de atenção e destaques positivos mais relevantes, sem precisar entrar em cada aba.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # depois edite .env e cole sua HEVY_API_KEY
```

A key da API do Hevy é gerada em [hevy.com/settings?developer](https://hevy.com/settings?developer) (requer Hevy Pro).

## Rodando

```bash
streamlit run app/Home.py
```

Na primeira execução, clique em **Sincronizar** para importar todo o histórico. Nas próximas vezes, o mesmo botão busca só o que mudou desde o último sync.

## Testes

```bash
pytest
```

## Estrutura

```
src/hevy_analytics/     pacote Python puro (zero dependência de Streamlit)
  api/                  cliente da API do Hevy
  db/                   schema e conexão SQLite
  ingest/                sincronização idempotente (upsert/delete)
  config/                loaders de landmarks.yaml e context.yaml
  analytics/             descritivo, diagnóstico, preditivo, prescritivo, responsividade, metas
  insights/              modelo de Insight (estruturado, não preso a widget de UI)
app/                     dashboard Streamlit, consome o pacote acima
config/
  landmarks.yaml          thresholds de volume (MEV/MAV/MRV), fórmulas de 1RM, regras de platô/fadiga/staleness
  context.yaml            atividades externas que podem explicar fadiga
data/hevy.db             banco SQLite local (gitignored)
```

## Metodologia

Os thresholds de volume seguem o framework MEV/MAV/MRV (Renaissance Periodization) e meta-análises gerais de volume de treino como ponto de partida — não são valores validados especificamente para o usuário. Pensados pra serem ajustados em `config/landmarks.yaml` conforme a pessoa estuda mais e observa sua própria resposta ao treino.

As recomendações da aba Prescritivo e as metas são 100% baseadas em regras (sem personalização por machine learning). A análise de responsividade a volume é a exceção parcial: uma comparação estatística simples sobre os próprios dados da pessoa, sempre apresentada com o caveat de que é exploratória.

Metas de saúde/dor (ex: instabilidade patelar) são tratadas como acompanhamento, não diagnóstico — o app é explícito que avaliação e tratamento são de um profissional, não do software.

## Segurança

A API key do Hevy fica só em `.env` local (nunca commitado — veja `.gitignore`). O banco de dados (`data/hevy.db`), que contém o histórico de treino real, também é gitignored.
