# Codex handoff - 2026-05-24

Este bloco foi feito pelo Codex.

## Escopo executado

- Removeu nota sensivel de `NEXT_STEPS.md`.
- Protegeu `/webhook/{tenant_slug}` com `X-Webhook-Token` ou JWT GP/Analyst.
- Protegeu `/api/v1/*` e `/stream/{tenant_slug}` com JWT/cookie e validacao de tenant.
- Atualizou dashboard para login/logout via `/auth/*` e cookie `HttpOnly`.
- Atualizou README, RUNBOOK, ARCHITECTURE e NEXT_STEPS para refletir auth real, bcrypt ativo, 92 testes e gitleaks no CI.
- Adicionou `.gitleaks.toml` e `gitleaks/gitleaks-action` no GitHub Actions.
- Adicionou testes de seguranca para auth, cookie, dashboard API e webhook.

## Validacao executada

- `pre-commit run --all-files`
- `gitleaks detect --source . --redact --no-banner --verbose`
- `gitleaks dir . --redact --no-banner --verbose`
- `.venv/bin/pytest -q` - 92 passed
- Validacao HTTP local do dashboard, login, API protegida, webhook protegido e SSE autenticado.

## Observacoes para Claude

- O dashboard agora deve ser acessado por `http://127.0.0.1:8000/dashboard/` e login `gp@acme.test` / `dev`.
- Para chamar webhook por curl, use `X-Webhook-Token: $WEBHOOK_BEARER_TOKEN`.
- O arquivo `cowork.yaml` estava modificado no worktree e nao faz parte deste handoff do Codex.
