# Access Plans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user commercial plans that unlock Padoka 100 feature groups while keeping backend authorization authoritative.

**Architecture:** The backend stores `usuarios.plano` and derives capabilities from a central matrix. Routers require capabilities via FastAPI dependencies; the app reads `capacidades` from `/perfil/me` to hide or gate unavailable features.

**Tech Stack:** FastAPI, Supabase Postgres migrations, Expo React Native, TypeScript.

---

### Task 1: Backend Capability Matrix

**Files:**
- Create: `app/modules/auth/capacidades.py`
- Test: `tests/test_access_plans.py`

- [x] Write tests proving `basico`, `analitico`, `ia`, and `admin` expose the expected capabilities.
- [x] Implement constants for plans and capabilities plus `capacidades_do_usuario`.
- [x] Run `python -m unittest tests.test_access_plans`.

### Task 2: Backend User Contract

**Files:**
- Modify: `app/modules/auth/esquemas.py`
- Modify: `app/modules/auth/servico.py`
- Create: `supabase/migrations/013_planos_acesso.sql`

- [x] Add `plano` and `capacidades` to `UsuarioSaida`.
- [x] Default synchronized Supabase users to `basico`.
- [x] Add migration with `usuarios.plano` and check constraint.
- [x] Run auth tests.

### Task 3: Backend Route Guards

**Files:**
- Modify routers under `app/modules/*/router.py`
- Modify: `app/modules/auth/dependencias.py`

- [x] Add `exigir_capacidade("...")` dependency.
- [x] Apply basic, analytic, AI, cost, and admin capabilities to the matching routers.
- [x] Preserve `X-API-Key` as operational all-access.
- [x] Run `python -m ruff check app tests` and `python -m compileall app`.

### Task 4: Mobile Feature Gates

**Files:**
- Modify: `src/types/api.ts`
- Create: `src/lib/access.ts`
- Modify tabs and screens that link to analytics, costs, shopping list, and AI.

- [x] Add `plano` and `capacidades` to `UsuarioPerfil`.
- [x] Add `hasAccess` helper.
- [x] Gate navigation/actions for unavailable features with upgrade messaging.
- [x] Run `npm run typecheck` and `npm run lint`.

### Task 5: Architecture Docs

**Files:**
- Create: `docs/ACCESS_PLANS.md` in both repos.

- [x] Document plans, capabilities, backend authority, and app-side UX gates.
- [x] Include operational notes for assigning `admin`.
