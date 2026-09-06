# Secrets & Environment Config

- Never commit real secrets. `.env` / `.env.local` are git-ignored everywhere.
- `.env.example` / `.env.local.example` are committed and list every required
  key with a placeholder value — keep these in sync whenever a new env var
  is introduced.
- Local dev: real values in `.env` (backend) / `.env.local` (web), loaded via
  python-decouple / Next.js built-in env loading.
- CI: throwaway values inlined directly in the workflow YAML (not real secrets).
- Staging/Prod: real values live in GitHub Actions Secrets (or the hosting
  provider's env/secret manager once chosen) — never in a file in the repo.
- `ENVIRONMENT` var (local | staging | prod) is available for any
  environment-conditional logic in settings.py.