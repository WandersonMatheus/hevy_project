# Hevy Analytics

App pessoal de analytics para musculação: importa o histórico de treinos do Hevy, mantém a base atualizada via sincronização manual e gera análises descritivas, diagnósticas, preditivas e prescritivas (1RM, volume por grupo muscular vs. MEV/MAV/MRV, sinais de platô/fadiga).

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

Na primeira execução, clique em **Sincronizar** para importar todo o histórico. Nas próximas vezes, o mesmo botão busca só o que mudou desde o último sync (endpoint `/v1/workouts/events`).

## Testes

```bash
pytest
```

## Estrutura

- `src/hevy_analytics/` — pacote Python puro (sem dependência de Streamlit): cliente da API, schema/conexão SQLite, ingestão idempotente, camada de analytics (descritivo/diagnóstico/preditivo/prescritivo).
- `app/` — dashboard Streamlit, consome o pacote acima.
- `config/landmarks.yaml` — thresholds de volume (MEV/MAV/MRV) e regras de RPE/platô, editável sem mexer em código.
- `data/hevy.db` — banco SQLite local (gitignored).

## Metodologia

Os thresholds de volume seguem o framework MEV/MAV/MRV (Renaissance Periodization) e meta-análises gerais de volume de treino como ponto de partida — não são valores validados especificamente para você. Ajuste `config/landmarks.yaml` conforme for estudando e observando sua própria resposta ao treino. As recomendações da aba Prescritivo são 100% baseadas em regras (não há machine learning/personalização na v1).
