# Portfolio-Pulse - Next steps (post Session 3)

**Status (v0.1.0):** Sessions 1, 2, 3 implementadas. CI verde. 63 unit tests (no I/O) + 10 skill evals (mocked) + Anthropic Managed Agents pipeline validado end-to-end real.

Este arquivo lista o que falta pra fechar o projeto como peça de portfolio mostrável para o recrutador da Mavila.

---

## URGENTE: rotacionar credentials de novo

Durante a Sessão 3, ao tentar editar `.env` para adicionar `SCIM_BEARER_TOKEN`, o `Read` no arquivo expôs **mais uma vez** os valores literais de `ANTHROPIC_API_KEY` e `SLACK_BOT_TOKEN` no transcript da conversa.

Os tokens atuais devem ser considerados comprometidos. Procedimento (5 min):

### Anthropic
1. https://console.anthropic.com/settings/keys → delete `portfolio-pulse-dev`
2. Criar nova com mesmo nome
3. Atualizar `ANTHROPIC_API_KEY=` no `.env` local **via shell direto, sem editor**:
   ```bash
   # Substitui só a linha, não revela o valor:
   sed -i.bak '/^ANTHROPIC_API_KEY=/d' .env && \
   printf "ANTHROPIC_API_KEY=COLE_AQUI\n" >> .env && rm .env.bak
   ```

### Slack
1. https://api.slack.com/apps/A0B5E31ALLF/install-on-team → Reinstall to Workspace
2. Copiar novo `xoxb-...`
3. Atualizar no `.env` da mesma forma cega acima.

Não precisa nada de Anthropic re-criar (os `agent_id` em `.agents_config.json` continuam válidos - só a auth muda).

---

## O que falta pra fechar a Sessão 3 (Épico 9)

### 1. Vídeo demo Loom (3-5 min)

Eu não consigo gravar - precisa ser você. Sugestão de roteiro:

```
0:00-0:20  Pitch curto:
  "Portfolio-Pulse: multi-tenant portfolio monitoring para PE firms.
   Três Anthropic Managed Agents detectam anomalia, enriquecem contexto,
   classificam severidade. Acabei de validar end-to-end."

0:20-0:50  Tour do repo no GitHub:
  README badges (CI verde, License, Python),
  estrutura do app/, mapping table do JD Mavila.

0:50-1:40  Demo ao vivo:
  - Abrir dashboard em /dashboard/ (mostra heatmap + alert feed vazio)
  - Em outro terminal: curl POST /webhook/acme com revenue=3.1
  - Voltar pro dashboard: eventos kpi_received -> pipeline_started -> agent_started x3 chegando ao vivo
  - Esperar ~60s -> alert urgent aparece no feed + Slack notifica

1:40-2:10  Mostrar Jaeger:
  http://localhost:16686 -> service portfolio-pulse -> trace -> 12 spans em cascata
  (anomaly, context, severity + 8 tool calls)

2:10-2:40  Mostrar DB:
  docker compose exec postgres psql ... SELECT * FROM agent_runs
  -> 4 linhas com tokens/cost/latency reais
  -> $0.06 por run

2:40-3:10  Mostrar Skills + SCIM + RBAC:
  - cat skills/portco-anomaly-monitor/SKILL.md (3s)
  - curl /auth/login + /admin/portcos como GP (3 portcos)
  - curl /admin/portcos como Analyst SaaS (1 portco) - "scoping"
  - curl -H "Authorization: Bearer $SCIM" /scim/v2/Users -> ListResponse RFC 7644

3:10-3:30  Wrap:
  "Custos: $4 total durante o desenvolvimento. Repo público
   no GitHub, MIT licensed. Documentação em ARCHITECTURE.md
   e RUNBOOK.md. Pronto pra discussão técnica."
```

Grave no Loom (https://loom.com), copie link público, cole no README na seção "Demo video".

### 2. GIFs animados (opcional mas alto impacto)

GIFs no GitHub README rodam sozinhos. Dois principais:
- Dashboard atualizando ao vivo enquanto o pipeline roda
- Jaeger UI mostrando os 12 spans em cascata

Ferramentas no Mac:
- `Cmd+Shift+5` -> record selected area -> salva .mov
- `ffmpeg -i screen.mov -vf "fps=10,scale=800:-1" -c:v gif demo.gif`
- Coloca em `docs/gifs/` e referencia no README com `![](docs/gifs/dashboard.gif)`

### 3. Atualizar CV Mavila

Arquivo: `/Users/fernandoloureiro/Library/CloudStorage/GoogleDrive-loureiro.fernando@gmail.com/My Drive/1. Carreira/2. Entrevistas/2026/Mavila/Fernando_Loureiro_CV_Mavila_AIAgentEngineer.docx`

Sugestão de bullet pra inserir na seção mais recente (top):

> **Portfolio-Pulse** (portfolio project, 2026) - Multi-tenant portfolio monitoring para PE firms com 3 Anthropic Managed Agents (AnomalyDetector + ContextBuilder + SeverityClassifier) orquestrados via `multiagent` coordinator, SCIM 2.0 + RBAC com 3 roles, dashboard live via SSE, OpenTelemetry traces por agent. Stack: Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Postgres / Anthropic SDK 0.104. Repo público: github.com/loureiro-fernando/portfolio-pulse

### 4. Atualizar Cover Letter

Mesmo diretório, `Fernando_Loureiro_CoverLetter_Mavila_AIAgentEngineer.docx`.

Adicionar parágrafo após o pivô de positioning:

> Para evidenciar o pivô para builder, construí este fim de semana o **Portfolio-Pulse** (github.com/loureiro-fernando/portfolio-pulse), que cobre os Required Skills do JD em código real: Anthropic Managed Agents API com multi-agent orchestration, Agent Skills com evals, MCP connectors, SCIM 2.0 conforme RFC 7644, RBAC, OpenTelemetry. O README tem um mapa explícito de cada Required Skill para o arquivo onde está implementado.

### 5. (Opcional) Tag de release no GitHub

Já criada localmente no fim da Sessão 3:
```bash
git tag -l
git push origin v0.1.0   # se ainda não pushado
```

Criar release no GitHub:
```bash
gh release create v0.1.0 --title "v0.1.0 - feature-complete MVP" --notes "See README.md and ARCHITECTURE.md"
```

---

## O que está pronto e funcionando

Todos os arquivos abaixo já existem no repo, testados localmente e em CI:

- **Pipeline multi-agent** (Épico 4): `app/agents/{prompts,tools,setup,orchestrator}.py`
- **MCP Slack** (Épico 5): `app/mcp_servers/slack_server.py` + `tests/smoke_slack.py`
- **Mocks PitchBook/Egnyte** (Épico 5): `app/services/mocks/`
- **SCIM 2.0 + RBAC + JWT** (Épico 6): `app/api/{auth,admin,scim}.py` + `app/services/rbac.py` + `app/services/scim_schemas.py`
- **Agent Skills** (Épico 7): `skills/portco-anomaly-monitor/` + `skills/lp-update-drafter/` com 10 evals
- **Dashboard** (Épico 8): `app/static/index.html` em `/dashboard/`
- **OTel tracing** (Épico 4): `app/telemetry.py` exportando para Jaeger
- **Docs operacionais** (Épico 10): `ARCHITECTURE.md`, `RUNBOOK.md`, `CONTRIBUTING.md`, `cowork.yaml`
- **README v3** (Épico 9 parcial): badges + arquitetura + JD coverage table + ethics + what's NOT in MVP

## Validação end-to-end real (concluída em 2026-05-24)

```
POST /webhook/acme {portco-1, revenue, 3.1, 2026-04}
  -> 202 Accepted
  -> pipeline runs 60s
  -> Slack: "🚨 AcmeCo - Revenue collapsed 31.1% YoY..."
  -> Jaeger: 12 spans (1 root + 3 agent threads + 8 tool calls)
  -> Postgres:
      4 agent_runs (anomaly $0.011, context $0.019, severity $0.013, coordinator $0.020)
      1 alert urgent + requires_human=true
  -> SSE stream emitiu: kpi_received, pipeline_started, agent_started x3,
     agent_completed x3, pipeline_completed (com JSON do verdict)
  -> Custo total: $0.063 por run
```

Para refazer essa validação após rotacionar as keys:
```bash
make up && make dev      # em dois terminais separados
# Terceiro terminal:
curl -X POST http://localhost:8000/webhook/acme -H "Content-Type: application/json" \
  -d '{"portco_id":"portco-1","metric":"revenue","value":3.1,"period":"2026-04"}'
```

## Bug cosmético conhecido

`AgentRun.latency_ms = 0` para o thread do coordinator (apenas para ele - os 3 specialists têm latency correta). Causa: o `session.thread_created` event não vem para o thread raiz do coordinator no formato esperado. Não impacta funcionalidade nem custo - só polui a tabela.

Fix futuro (~10 min): capturar tempo do coordinator a partir do `session.created_at` e `session.updated_at` (ou usar `session.stats.active_seconds`).

## Sessão futura: hardening pré-produção

Se o projeto fosse evoluir para produção, em ordem de prioridade:

1. Real password verification (`bcrypt.checkpw`) - 5 linhas em `app/api/auth.py`
2. Alembic migrations - hoje usa `Base.metadata.create_all` que não suporta evolução
3. Postgres RLS multi-tenant - hoje filtragem é application-layer
4. Job queue persistente (RQ/ARQ) - hoje `BackgroundTasks` morre se uvicorn restarta
5. SSE fan-out via `LISTEN/NOTIFY` - hoje single-process
6. SCIM PATCH endpoint - Okta usa para partial updates
7. Audit log table com RLS
8. Per-tenant cost budget enforcement
