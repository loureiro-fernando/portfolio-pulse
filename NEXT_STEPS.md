# Portfolio-Pulse - Próximos passos para retomar a Sessão 2

Sessão 2 (Épico 4 - pipeline multi-agent) está **implementada e testada localmente**, mas a **validação end-to-end com a API real da Anthropic ainda não rodou**. Faltou esse último passo porque:

1. As keys `ANTHROPIC_API_KEY` (`portfolio-pulse-dev`) e `SLACK_BOT_TOKEN` foram **expostas no terminal** durante debug do pydantic-settings. Precisam ser revogadas/regeradas antes de executar.
2. O setup script (`python -m app.agents.setup`) faz `agents.create()` e `environments.create()` reais - requer API key válida.

## Passo 1: Regerar as keys expostas

### Anthropic key

1. https://console.anthropic.com/settings/keys
2. Delete a key atual `sk-ant-api03-5No...`
3. Crie nova com mesmo nome `portfolio-pulse-dev`, workspace `Default`
4. Copie o valor (mostrado uma vez só)

### Slack bot token

1. https://api.slack.com/apps/A0B5E31ALLF/install-on-team
2. **Reinstall to Workspace** (rotaciona o token, invalida o anterior)
3. Copie o novo `xoxb-...`

### Atualizar `.env`

```bash
cd ~/projects_coding/portfolio-pulse
# Edita .env e troca os dois valores:
#   ANTHROPIC_API_KEY=<nova-key>
#   SLACK_BOT_TOKEN=<novo-token>
```

## Passo 2: Validar end-to-end (Épico 4)

```bash
cd ~/projects_coding/portfolio-pulse
source .venv/bin/activate

# Infra (provavelmente ainda está rodando)
docker compose ps   # confirma postgres + jaeger UP. Se não: make up

# DB: schema + dados de teste
make init-db
python -m app.scripts.seed   # 1 tenant "acme", 3 portcos, 108 KPIs

# Cria env + 4 agents na Anthropic (uma vez, persiste em .agents_config.json)
python -m app.agents.setup
# Esperado: prints "environment: env_..." + "anomaly agent: agent_..." x4 + "wrote .agents_config.json"
# Custo: $0 (creates não consomem tokens).

# Sobe API
make dev   # uvicorn na porta 8000
```

Em outro terminal:

```bash
# Abre SSE stream
curl -N http://localhost:8000/stream/acme

# Em terceiro terminal: dispara um KPI anômalo
# portco-1 (AcmeCo) tem trajetória de revenue 4.5 -> queda para 3.1 em 2026-04 (-31%)
curl -X POST http://localhost:8000/webhook/acme \
  -H "Content-Type: application/json" \
  -d '{"portco_id":"portco-1","metric":"revenue","value":3.1,"period":"2026-04"}'
# Esperado: 202 Accepted + {"accepted":true,"tenant":"acme","portco":"portco-1","pipeline":"scheduled"}
```

**No SSE stream**, esperado nessa ordem (cada evento como `data: {...}\n\n`):
1. `kpi_received`
2. `pipeline_started`
3. `agent_started` (AnomalyDetector) -> `agent_completed`
4. `agent_started` (ContextBuilder) -> `agent_completed`
5. `agent_started` (SeverityClassifier) -> `agent_completed`
6. `pipeline_completed` (com `output` contendo o JSON final do coordinator)

Tempo total esperado: 20-60s com Haiku 4.5.

**Validações pós-pipeline:**

```bash
# 1. Mensagem no Slack #portfolio-pulse (se severity >= attention)
#    Esperado: ":rotating_light: *AcmeCo* - <summary>" ou similar

# 2. Spans no Jaeger
open http://localhost:16686
# Service: portfolio-pulse
# Esperado: span raiz "portfolio_pulse.pipeline" com 8+ sub-spans (3 agent threads + tool calls)

# 3. AgentRun no DB
docker compose exec -T postgres psql -U pulse -d portfolio_pulse -c "SELECT agent_name, input_tokens, output_tokens, cost_usd, latency_ms FROM agent_runs ORDER BY created_at DESC LIMIT 10;"
# Esperado: linhas para os 3 agents com tokens/cost/latency populados

# 4. Alert no DB
docker compose exec -T postgres psql -U pulse -d portfolio_pulse -c "SELECT severity, summary, requires_human FROM alerts ORDER BY created_at DESC LIMIT 5;"
# Esperado: 1 alert com severity = 'attention' ou 'urgent'
```

## Passo 3: Variações de teste

```bash
# Caso "NORMAL" (sem anomalia) - 2026-05 com value pequena vs trajetória
curl -X POST http://localhost:8000/webhook/acme \
  -H "Content-Type: application/json" \
  -d '{"portco_id":"portco-2","metric":"revenue","value":3.7,"period":"2026-05"}'
# Esperado: pipeline roda, AnomalyDetector decide NORMAL, coordinator para,
# pipeline_completed sem JSON de severidade, sem alert no DB

# Caso "burn anomaly" (portco-3 GammaFin) - burn 6.4 -> 9.5 simula explosão
curl -X POST http://localhost:8000/webhook/acme \
  -H "Content-Type: application/json" \
  -d '{"portco_id":"portco-3","metric":"burn","value":9.5,"period":"2026-05"}'
# Esperado: severity attention/urgent + alert no Slack
```

## Passo 4: Debug se algo quebrar

| Sintoma | Causa provável | Fix |
|---|---|---|
| Webhook retorna 404 "unknown tenant" | seed não rodou | `python -m app.scripts.seed` |
| `FileNotFoundError: .agents_config.json` | setup não rodou | `python -m app.agents.setup` |
| `AuthenticationError` da Anthropic | key inválida ou expirou | Regerar key + atualizar `.env` |
| `slack_sdk.errors.SlackApiError` | bot não tem permissão no canal ou token inválido | Re-invitar bot + reinstalar app |
| Sem eventos `agent_*` no SSE | orchestrator quebrou silenciosamente em background | Ver logs do uvicorn (terminal do `make dev`) |
| Pipeline trava em "running" | tool dispatch falhou ou agent não termina | Conferir logs + olhar `gh run list` na conta Anthropic |
| Spans não aparecem no Jaeger | Jaeger não está UP ou OTLP exporter errou | `docker compose ps`, verificar porta 4318 |

## O que está implementado (Sessão 2 / Épico 4)

- `app/agents/prompts.py` - System prompts dos 4 agents (3 specialists + coordinator)
- `app/agents/tools.py` - 8 custom tool schemas + dispatch host-side (Slack/PitchBook/Egnyte/policies/queries)
- `app/agents/setup.py` - cria env + 4 agents em Cloud (idempotente, persiste IDs)
- `app/agents/orchestrator.py` - cria session, stream loop, callback de tools, persiste AgentRun + Alert + posta no Slack
- `app/event_bus.py` - SSE bus por tenant
- `app/telemetry.py` - OTel OTLP HTTP exporter
- `app/services/mocks/{pitchbook,egnyte}.py` - mocks com dados realistas
- `app/services/policies.py` - tenant policies hardcoded
- `app/services/anomaly_data.py` - queries DB (fetch_history, compare_peers)
- `app/scripts/seed.py` - dados de teste idempotentes
- `app/main.py` - webhook agora dispara orchestrator via BackgroundTask, retorna 202
- `tests/conftest.py` - env dummy para CI
- `tests/test_{mocks,policies,tools,orchestrator_helpers}.py` - 44 unit tests
- `README.md` v2 com arquitetura do Épico 4 + custom-tools rationale

**45 tests passando localmente + CI verde** (validado pós-commits).

## O que falta (não tinha como fazer sem você)

- [ ] **Regerar keys expostas** (Passo 1 acima) - bloqueia tudo
- [ ] **Validação end-to-end real** (Passo 2) - testa que a integração com Managed Agents funciona de verdade. Pode haver ajustes na forma como acesso campos dos eventos (`event.input`, `event.session_thread_id`, etc.) - codei defensivamente com `getattr` mas só rodando dá pra saber.
- [ ] **Ver Jaeger ao vivo** - se os spans aparecerem certinho ou se preciso ajustar a config do OTel

## Sessão 3 (próximo grande passo, ainda não começado)

- Épico 6: SCIM 2.0 endpoints (`app/api/scim.py`) + RBAC com 3 roles (decorator `@requires_role`)
- Épico 7: Agent Skills (`skills/portco-anomaly-monitor/SKILL.md` + evals + script)
- Épico 8: Dashboard HTML/Alpine.js consumindo SSE
- Épico 9: README final + GIFs + vídeo demo Loom
- Épico 10: ARCHITECTURE.md + RUNBOOK.md + cowork.yaml

## Custos previstos

Com `AGENT_MODEL=claude-haiku-4-5-20251001` (configurado no .env):

- Cada ciclo do pipeline (3 agents + coordinator): ~5-10k input + 1-3k output ≈ **$0.01-$0.02**
- Cobertura confortável dentro do crédito de USD 10.86 do workspace.

Para o vídeo demo final, trocar `AGENT_MODEL=claude-sonnet-4-6` no `.env` (1 troca de env var, sem mexer no código). Sonnet custa ~5x mais por ciclo (~$0.05-$0.10) mas qualidade da decisão melhora.

---

**Status enquanto você esteve fora:** 10 commits no main, CI verde, 45 tests passando. Não consegui rodar o setup real porque as keys precisam ser regeradas. Quando voltar, ~10 min de Passo 1+2 acima destrava a validação completa.
