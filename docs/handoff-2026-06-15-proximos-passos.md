# Handoff — Controladoria (2026-06-15)

Resumo para retomar numa nova sessão. Dois repositórios:
- **Agente/extratores:** `~/Projects/paes-alves-pequeno-advogados/controladoria-playwright` (Python)
- **App (Vercel):** `~/Projects/paes-alves-pequeno-advogados/paes-alves-controladoria` (Next.js 16)
- **Supabase:** projeto `elxfggiidacmhwprbfev` (mesmo para app e agente)

## O que já foi feito (funcionando e verificado)

1. **Comando único `iniciar.py`** — abre o Chrome nos sistemas pendentes e, quando o login é detectado, a extração começa **sozinha** (sem Enter, sem segundo comando).
2. **Agente local `agente.py`** — fica rodando na máquina, consulta a tabela `comandos` no Supabase a cada 3s; quando há comando `pendente`, roda o fluxo e grava o status de volta.
3. **App:** botão "Iniciar extração" no dashboard + rota `/api/comandos` (cria comando / lê último status). Já em produção na Vercel.
4. **Tabela `comandos`** no Supabase (fila). RLS ligada, GRANT para `service_role`.
5. **Correções de bugs (com testes):**
   - Detecção de login robusta e não-intrusiva (checa campo de senha, sem navegar) — corrige falso-positivo do RUPE.
   - Status honesto do comando (processados/erros), não mais "Concluído" falso.

**Teste E2E validado ao vivo** com 1 processo de 2ª instância (RUPE, `0372800-08.2026.8.13.0000`): deslogado → agente esperou → login → disparou sozinho → 45 docs extraídos → rascunho gerado → status "1 processado(s)".

Arquivos-chave do agente: `iniciar.py`, `agente.py`, `sistema_auth.py`, `runner.py`. Testes: `test_agente.py`, `test_sistema_auth.py`.

## Como rodar (estado atual da máquina)

No momento do handoff, podem estar rodando em background: o agente (`python -u agente.py`) e o dev server do app (`npm run dev`, porta 3000). Para uma nova sessão, o mais limpo é reiniciá-los:

```bash
# Terminal 1 — agente local
cd controladoria-playwright && .\venv\Scripts\activate && python -u agente.py

# Terminal 2 — app (ou usar a URL da Vercel)
cd paes-alves-controladoria && npm run dev
```

Para testar: marcar processo(s) como `pendente` na tabela `processos` → clicar "Iniciar extração" → logar nos sistemas.

## Próximos passos (objetivo da nova sessão)

### 1. Teste com MÚLTIPLOS processos (PJE 1º grau + RUPE 2ª instância juntos)
**Deve funcionar por design** (ainda não testado ao vivo com 2 sistemas):
- `runner.processar_por_sistema` agrupa CNJs por sistema, autentica **todos** os sistemas necessários de uma vez e processa um sistema por vez.
- `iniciar._coletar_urls_pendentes` abre **uma aba por sistema distinto**.
- `aguardar_login_automatico` só dispara quando **todos** os sistemas estão logados (`all(status.values())`).
- **A validar:** com PJE + RUPE pendentes, o agente abre as duas abas, espera login nas duas, e extrai os dois. Verificar a detecção de login do PJE 1º grau (cada extrator tem seu `verificar_sessao`; a mesma checagem de campo-de-senha deve cobrir, mas confirmar ao vivo).

### 2. Automação de e-mail via Outlook/Hotmail (leomamerlo@hotmail.com)
Hoje a ingestão de e-mail é via Gmail. Objetivo: Henrique manda e-mail com os processos → salvar automático no Supabase (`emails_recebidos` + `processos` como `pendente`) → depois clicar "Iniciar extração".

**Onde olhar primeiro (app):** `app/api/email/processar/route.ts`, `app/api/email/simular/route.ts`, `lib/email/`. E a skill `controladoria-browser` / `controladoria-juridica-browser`.

**Opções para Outlook/Hotmail** (decidir na nova sessão, depois de ler o código atual):
- **n8n** (Leonardo tem n8n-mcp): trigger de e-mail (IMAP/Outlook) → parseia CNJs → POST para `/api/email/processar` ou insere direto no Supabase. Provavelmente o caminho mais rápido e desacoplado.
- **Microsoft Graph API** (OAuth) — caminho "oficial" para ler caixa Outlook/Hotmail.
- **IMAP** do outlook.com — mais simples para um teste.

**Dúvida em aberto (Leonardo):** isso é uma skill do Cowork a criar, ou uma rota/automação no app? → Avaliar: a ingestão pode ser uma rota do app + n8n; a skill cobre a orquestração. Ver como `controladoria-browser` está estruturada antes de decidir.

### 3. Distribuição para a máquina do Henrique (depois)
- Subir `controladoria-playwright` para um repo **privado** no GitHub (ver abaixo) para o Henrique instalar via `git clone`.
- `.env.example` já existe; criar guia de instalação (Python, venv, `pip install -r requirements.txt`, `playwright install`, preencher `.env`).
- Autostart do agente no Windows (Agendador de Tarefas) ou empacotar com PyInstaller.

## Pendências / observações de infra

- **Repo `controladoria-playwright`:** agora é um repositório git **standalone** (criado nesta sessão, 1 commit em `master`). Ainda **não está no GitHub**. Faz sentido subir (privado) quando for instalar no PC do Henrique.
- **⚠️ `.git` acidental na home:** existe um repositório git em `C:\Users\User` (sem commits). Risco de versionar a home inteira por engano (inclui `.claude.json` com tokens). Recomendado remover: `Remove-Item C:\Users\User\.git -Recurse -Force` — **confirmar antes** (destrutivo).
- **Supabase multi-cliente (decisão estratégica):** para escalar a controladoria para outros clientes, recomendação foi **1 projeto Supabase por cliente dentro da org do Leonardo** (controle de billing/alertas centralizado), no plano Pro com spend cap; dado confidencial do escritório amparado por contrato (operador/controlador LGPD). Migrar para conta do cliente quando exigirem posse dos dados (Supabase permite transferir projeto).
