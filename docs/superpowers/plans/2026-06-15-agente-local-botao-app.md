# Agente Local + Botão no App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Henrique aperta "Iniciar extração" no app (Vercel) → um agente local na máquina do operador detecta o comando, abre o Chrome nos sistemas necessários, e quando o login é feito a extração roda sozinha; o status volta para o app em tempo quase real.

**Architecture:** Fila de comandos via Supabase. O app escreve uma linha em `comandos`. O agente local (Python, na máquina do operador) consulta `comandos` a cada 3s, "pega" o comando pendente, executa o fluxo `iniciar.py` (que já dispara a extração automática após o login) e grava status/mensagem de volta. **Nenhuma conexão entra na máquina local** — ela só consulta o Supabase para fora (polling). Por isso não há firewall, porta aberta nem IP público.

**Segurança:** As credenciais dos tribunais (login + senha + OTP) são digitadas manualmente no navegador a cada execução. Nem o agente nem o app armazenam ou transmitem essas credenciais. A tabela `comandos` é acessada apenas pelo service role no servidor (RLS ligada, sem policies para anon).

**Tech Stack:** Supabase (Postgres), Python (projeto `controladoria-playwright` existente), Next.js 16 App Router + Route Handlers com Supabase admin client (`@/lib/supabase/admin`).

**Escopo do teste de hoje:** o agente roda num terminal (`python agente.py`) — autostart no boot do Windows fica para depois (ver "Fora de escopo"). Tudo o mais é E2E real.

**Limitação conhecida:** um comando `pendente` antigo dispara assim que o agente inicia. Para o teste é aceitável; mitigação (ignorar comandos com mais de N minutos) fica para depois.

---

## File Structure

**Repo `controladoria-playwright` (agente local):**
- Create: `agente.py` — loop de polling + seleção/atualização de comandos.
- Create: `test_agente.py` — testes da lógica pura de seleção de comando (sem rede).
- Reusa: `iniciar.py` (`main()`), `supabase_writer.py` (`_get_client`, `_carregar_env`).

**Repo `paes-alves-controladoria` (app Vercel):**
- Supabase: nova tabela `comandos` (migration).
- Create: `app/api/comandos/route.ts` — `POST` insere comando; `GET` retorna o último.
- Create: `components/botao-iniciar.tsx` — client component (botão + polling de status).
- Modify: `app/dashboard/page.tsx` — renderiza `<BotaoIniciar />`.
- Modify: `lib/supabase/types.ts` — regenerado após criar a tabela.

---

## Task 1: Tabela `comandos` no Supabase

**Files:**
- Migration aplicada no projeto Supabase (via Supabase MCP `apply_migration` ou SQL Editor).
- Modify: `paes-alves-controladoria/lib/supabase/types.ts` (regenerado).

- [ ] **Step 1: Aplicar a migration**

SQL (nome da migration: `criar_tabela_comandos`):

```sql
create table if not exists public.comandos (
  id uuid primary key default gen_random_uuid(),
  acao text not null default 'iniciar',
  status text not null default 'pendente',
  mensagem text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create index if not exists comandos_status_criado_idx
  on public.comandos (status, criado_em);

-- Acesso só via service role (server). RLS ligada sem policies bloqueia anon/authenticated.
alter table public.comandos enable row level security;

comment on table public.comandos is
  'Fila de comandos do app para o agente local da controladoria. status: pendente|em_andamento|concluido|erro';
```

- [ ] **Step 2: Verificar a criação**

Rodar (Supabase MCP `execute_sql` ou SQL Editor):

```sql
select column_name, data_type from information_schema.columns
where table_name = 'comandos' order by ordinal_position;
```

Esperado: colunas `id, acao, status, mensagem, criado_em, atualizado_em`.

- [ ] **Step 3: Regenerar os tipos do app**

Regenerar `lib/supabase/types.ts` (Supabase MCP `generate_typescript_types`, ou
`npx supabase gen types typescript --project-id <PROJECT_ID> > lib/supabase/types.ts`).

Verificar que `types.ts` agora contém `comandos`:

```bash
grep -c "comandos" paes-alves-controladoria/lib/supabase/types.ts
```

Esperado: número ≥ 1.

- [ ] **Step 4: Commit (no repo do app)**

```bash
git add lib/supabase/types.ts
git commit -m "feat: tabela comandos para fila do agente local"
```

**Critério de verificação:** a tabela existe, RLS está ligada e `types.ts` reconhece `comandos`.

---

## Task 2: Lógica de seleção de comando (TDD)

**Files:**
- Create: `controladoria-playwright/test_agente.py`
- Create: `controladoria-playwright/agente.py` (só a função `proximo_pendente` nesta task)

- [ ] **Step 1: Escrever o teste que falha**

`controladoria-playwright/test_agente.py`:

```python
"""test_agente.py — testes do agente local. Rodar: python test_agente.py"""

from agente import proximo_pendente


def test_proximo_pendente_escolhe_mais_antigo():
    comandos = [
        {"id": "b", "status": "pendente", "criado_em": "2026-06-15T10:00:00Z"},
        {"id": "a", "status": "pendente", "criado_em": "2026-06-15T09:00:00Z"},
        {"id": "c", "status": "concluido", "criado_em": "2026-06-15T08:00:00Z"},
    ]
    assert proximo_pendente(comandos)["id"] == "a"
    print("OK escolhe_mais_antigo")


def test_proximo_pendente_sem_pendentes_retorna_none():
    comandos = [{"id": "x", "status": "concluido", "criado_em": "2026-06-15T08:00:00Z"}]
    assert proximo_pendente(comandos) is None
    print("OK sem_pendentes")


if __name__ == "__main__":
    test_proximo_pendente_escolhe_mais_antigo()
    test_proximo_pendente_sem_pendentes_retorna_none()
    print("Todos os testes passaram.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd controladoria-playwright && ./venv/Scripts/python.exe test_agente.py`
Esperado: FALHA com `ModuleNotFoundError: No module named 'agente'` (ou ImportError de `proximo_pendente`).

- [ ] **Step 3: Implementação mínima**

`controladoria-playwright/agente.py`:

```python
"""
agente.py — Agente local da controladoria.

Fica rodando na máquina do operador, consultando a tabela `comandos` no Supabase
a cada poucos segundos. Quando encontra um comando 'iniciar' pendente, executa o
fluxo de extração (iniciar.py) e grava o resultado de volta no Supabase.

Não abre portas nem recebe conexões: só consulta o Supabase de tempos em tempos.

Uso:
  python agente.py
"""


def proximo_pendente(comandos: list[dict]) -> dict | None:
    """Dentre os comandos recebidos, escolhe o mais antigo com status 'pendente'."""
    pendentes = [c for c in comandos if c.get("status") == "pendente"]
    if not pendentes:
        return None
    return sorted(pendentes, key=lambda c: c.get("criado_em", ""))[0]
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd controladoria-playwright && ./venv/Scripts/python.exe test_agente.py`
Esperado: imprime `Todos os testes passaram.`

- [ ] **Step 5: Commit (no repo controladoria-playwright)**

```bash
git add agente.py test_agente.py
git commit -m "feat: selecao de comando pendente do agente local"
```

---

## Task 3: Loop do agente + integração com extração

**Files:**
- Modify: `controladoria-playwright/agente.py`

- [ ] **Step 1: Adicionar imports e funções de I/O e o loop**

Adicionar ao topo de `agente.py` (acima de `proximo_pendente`):

```python
import asyncio
import time
import traceback
from datetime import datetime, timezone

from iniciar import main as executar_extracao
from supabase_writer import _get_client, _carregar_env

INTERVALO_S = 3
```

Adicionar abaixo de `proximo_pendente`:

```python
def buscar_pendentes(client) -> list[dict]:
    res = (
        client.table("comandos")
        .select("id, acao, status, criado_em")
        .eq("status", "pendente")
        .order("criado_em")
        .execute()
    )
    return res.data or []


def marcar(client, comando_id: str, status: str, mensagem: str | None = None) -> None:
    update: dict = {
        "status": status,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }
    if mensagem is not None:
        update["mensagem"] = mensagem
    client.table("comandos").update(update).eq("id", comando_id).execute()


def processar_um(client) -> bool:
    """Pega e executa um comando pendente. Retorna True se executou algo."""
    comando = proximo_pendente(buscar_pendentes(client))
    if not comando:
        return False

    cid = comando["id"]
    print(f"Comando recebido: {comando.get('acao')} ({cid[:8]})")
    marcar(client, cid, "em_andamento", "Abrindo navegador. Faça login nos sistemas.")
    try:
        asyncio.run(executar_extracao())
        marcar(client, cid, "concluido", "Extração finalizada.")
        print("Comando concluído.")
    except Exception as e:  # noqa: BLE001 — agente não pode morrer por um comando
        marcar(client, cid, "erro", f"Erro: {e}")
        print(f"Erro ao executar comando: {e}")
        traceback.print_exc()
    return True


def main_loop() -> None:
    _carregar_env()
    client = _get_client()
    print("Agente da controladoria iniciado. Aguardando comandos (Ctrl+C para sair)...")
    while True:
        try:
            processar_um(client)
        except Exception as e:  # noqa: BLE001 — loop nunca para por erro de rede
            print(f"Erro no loop do agente: {e}")
        time.sleep(INTERVALO_S)


if __name__ == "__main__":
    main_loop()
```

- [ ] **Step 2: Garantir que os testes da Task 2 continuam passando**

Run: `cd controladoria-playwright && ./venv/Scripts/python.exe test_agente.py`
Esperado: `Todos os testes passaram.` (a importação de `iniciar`/`supabase_writer` deve resolver).

- [ ] **Step 3: Verificar import do módulo completo**

Run: `cd controladoria-playwright && ./venv/Scripts/python.exe -c "import agente; print('import OK')"`
Esperado: `import OK`.

- [ ] **Step 4: Commit**

```bash
git add agente.py
git commit -m "feat: loop do agente local que executa comandos da fila"
```

**Critério de verificação:** módulo importa sem erro; testes passam; `main_loop` existe.

---

## Task 4: Route Handler `comandos` no app

**Files:**
- Create: `paes-alves-controladoria/app/api/comandos/route.ts`

- [ ] **Step 1: Criar o route handler**

`paes-alves-controladoria/app/api/comandos/route.ts`:

```ts
import { NextResponse } from 'next/server'
import { createAdminClient } from '@/lib/supabase/admin'

export async function POST() {
  const supabase = createAdminClient()
  const { data, error } = await supabase
    .from('comandos')
    .insert({ acao: 'iniciar', status: 'pendente' })
    .select()
    .single()

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json({ data }, { status: 200 })
}

export async function GET() {
  const supabase = createAdminClient()
  const { data, error } = await supabase
    .from('comandos')
    .select('id, acao, status, mensagem, criado_em, atualizado_em')
    .order('criado_em', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json({ data }, { status: 200 })
}
```

- [ ] **Step 2: Verificar build de tipos**

Run: `cd paes-alves-controladoria && npx tsc --noEmit`
Esperado: sem erros relacionados a `comandos` (depende de `types.ts` regenerado na Task 1).

- [ ] **Step 3: Verificar manualmente o endpoint**

Com `npm run dev` rodando, em outro terminal:

```bash
curl -X POST http://localhost:3000/api/comandos
curl http://localhost:3000/api/comandos
```

Esperado: o POST retorna `{ "data": { ... "status": "pendente" } }`; o GET retorna o mesmo comando como mais recente.

- [ ] **Step 4: Commit**

```bash
git add app/api/comandos/route.ts
git commit -m "feat: API de comandos (criar e ler ultimo)"
```

**Critério de verificação:** POST cria linha `pendente` em `comandos`; GET devolve a mais recente.

---

## Task 5: Botão e status no dashboard

**Files:**
- Create: `paes-alves-controladoria/components/botao-iniciar.tsx`
- Modify: `paes-alves-controladoria/app/dashboard/page.tsx`

- [ ] **Step 1: Criar o client component**

`paes-alves-controladoria/components/botao-iniciar.tsx`:

```tsx
'use client'
// client component: usa estado, fetch e polling no navegador para refletir o status do comando.

import { useEffect, useState } from 'react'

type Comando = {
  id: string
  acao: string
  status: string
  mensagem: string | null
  criado_em: string
  atualizado_em: string
}

const LABELS: Record<string, string> = {
  pendente: 'Aguardando o agente local…',
  em_andamento: 'Em andamento — faça login nos sistemas',
  concluido: 'Concluído',
  erro: 'Erro',
}

export default function BotaoIniciar() {
  const [comando, setComando] = useState<Comando | null>(null)
  const [enviando, setEnviando] = useState(false)

  async function carregarUltimo() {
    const res = await fetch('/api/comandos', { cache: 'no-store' })
    const { data } = await res.json()
    setComando(data ?? null)
  }

  useEffect(() => {
    carregarUltimo()
    const id = setInterval(carregarUltimo, 3000)
    return () => clearInterval(id)
  }, [])

  async function iniciar() {
    setEnviando(true)
    try {
      await fetch('/api/comandos', { method: 'POST' })
      await carregarUltimo()
    } finally {
      setEnviando(false)
    }
  }

  const emExecucao = comando?.status === 'pendente' || comando?.status === 'em_andamento'

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={iniciar}
        disabled={enviando || emExecucao}
        className="inline-flex items-center justify-center rounded-md bg-text px-4 py-2 text-sm font-medium text-bg disabled:opacity-50"
      >
        {emExecucao ? 'Extração em andamento…' : 'Iniciar extração'}
      </button>
      {comando && (
        <p className="text-xs text-text-tertiary">
          {LABELS[comando.status] ?? comando.status}
          {comando.mensagem ? ` — ${comando.mensagem}` : ''}
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Renderizar o botão no dashboard**

Em `paes-alves-controladoria/app/dashboard/page.tsx`, adicionar o import abaixo dos imports existentes:

```tsx
import BotaoIniciar from '@/components/botao-iniciar'
```

Substituir o bloco do cabeçalho:

```tsx
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-xl font-semibold text-text">
              Revisão de encaminhamentos
            </h1>
```

por (adicionando `<BotaoIniciar />` à direita):

```tsx
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-xl font-semibold text-text">
              Revisão de encaminhamentos
            </h1>
```

…mantendo o `<p>` existente, e logo **antes** do fechamento `</div>` externo desse bloco (depois do `<p>...</p>`), inserir:

```tsx
          <BotaoIniciar />
```

Resultado esperado do bloco:

```tsx
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-xl font-semibold text-text">
              Revisão de encaminhamentos
            </h1>
            <p className="mt-1 text-sm text-text-secondary">
              {/* ...conteúdo existente... */}
            </p>
          </div>
          <BotaoIniciar />
        </div>
```

- [ ] **Step 3: Verificar build de tipos**

Run: `cd paes-alves-controladoria && npx tsc --noEmit`
Esperado: sem erros.

- [ ] **Step 4: Verificar no navegador**

Com `npm run dev`, abrir `http://localhost:3000/dashboard`.
Esperado: o botão "Iniciar extração" aparece no canto superior direito do bloco de título.

- [ ] **Step 5: Commit**

```bash
git add components/botao-iniciar.tsx app/dashboard/page.tsx
git commit -m "feat: botao iniciar extracao no dashboard"
```

**Critério de verificação:** botão visível; ao clicar, fica desabilitado e mostra "Aguardando o agente local…".

---

## Task 6: Verificação End-to-End (manual, com operador logando)

> Esta verificação é manual porque depende do login real nos sistemas judiciais — só o operador (Leonardo/Henrique) consegue logar. Não há como automatizar este passo.

**Pré-condições:**
- Existe ≥ 1 processo `pendente` na tabela `processos` do Supabase (de um sistema implementado: PJE TJMG, eProc TJMG, eProc TRF6 ou RUPE 2ª inst.).
- `.env` do `controladoria-playwright` com `SUPABASE_URL`, chave service role e `ANTHROPIC_API_KEY` válidas.
- Chrome instalado no caminho de `iniciar.py`.

- [ ] **Step 1: Subir o agente local**

```bash
cd controladoria-playwright
./venv/Scripts/activate
python agente.py
```
Esperado: imprime "Agente da controladoria iniciado. Aguardando comandos…".

- [ ] **Step 2: Subir o app**

```bash
cd paes-alves-controladoria
npm run dev
```

- [ ] **Step 3: Clicar em "Iniciar extração" no dashboard**

Esperado (em até ~3s): no terminal do agente aparece "Comando recebido…" e o Chrome abre nas abas dos sistemas pendentes. No app, o status muda para "Em andamento — faça login nos sistemas".

- [ ] **Step 4: Fazer login nos sistemas**

O operador faz login em cada aba (login + senha + OTP). Esperado: assim que todos logam, o terminal do agente mostra "✓ Login detectado: …" e "Iniciando extração automaticamente".

- [ ] **Step 5: Conferir o resultado**

Esperado: o agente extrai, analisa e salva (logs por CNJ). Ao final, o status no app vira "Concluído". Verificar no Supabase que os `processos` saíram de `pendente` para `processado` e que há novos `rascunhos`.

- [ ] **Step 6: Conferir o caminho de erro (opcional)**

Sem nenhum processo pendente, clicar de novo. Esperado: o fluxo conclui rápido ("Nenhum processo pendente") e o status vira "Concluído" sem abrir abas inúteis.

**Critério de verificação:** o ciclo botão → agente → Chrome → login → extração → status "Concluído" funciona ponta a ponta, e o app reflete o status em ~3s.

---

## Fora de escopo (depois do teste)

- **Autostart do agente no Windows** (Agendador de Tarefas ou pasta Startup) e/ou empacotamento `.exe` com PyInstaller, para o Henrique não precisar abrir o terminal.
- **Realtime** do Supabase no lugar do polling de 3s no front (cosmético).
- **Autenticação/escopo** de quem pode clicar (hoje qualquer sessão do app).
- **Ignorar comandos antigos** ao iniciar o agente (anti-stale).
- **Progresso granular** por CNJ no app (hoje só pendente/andamento/concluído/erro).

---

## Self-Review

- **Cobertura do escopo:** fila (Task 1) · gatilho do app (Task 4, 5) · agente que executa (Task 2, 3) · reaproveita o auto-login do `iniciar.py` (#1 já implementado) · E2E (Task 6). ✔
- **Sem placeholders:** todo passo tem SQL/código/comando completo. ✔
- **Consistência de nomes:** `comandos` (tabela), `proximo_pendente`/`buscar_pendentes`/`marcar`/`processar_um`/`main_loop` (agente), `BotaoIniciar` (componente), `/api/comandos` (rota) usados igual em todas as tasks. ✔
