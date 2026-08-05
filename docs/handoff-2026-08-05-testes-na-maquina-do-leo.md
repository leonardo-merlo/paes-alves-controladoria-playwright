# Handoff — Controladoria (2026-08-05)

Ponto de partida para uma sessão nova. O Henrique viaja e volta na segunda; até
lá os testes rodam na máquina do Leonardo.

## Onde está cada coisa

- **Agente (Python):** `~/Projects/paes-alves-pequeno-advogados/controladoria-playwright`
  — repo `paes-alves-controladoria-playwright`, branch `master`.
- **Painel (Next.js/Vercel):** `~/Projects/paes-alves-pequeno-advogados/paes-alves-controladoria`
  — atenção, o repo no GitHub chama `ia-controladoria-advocacia`, branch `main`.
- **Supabase produção:** `hjesbvnxeivphplfymml`.
- **Máquina do Henrique:** `C:\Users\Acer\OneDrive\Desktop\SISTEMA`. Atualiza com
  `atualizar.bat` (faz fetch, reset e reinicia o agente sozinho).

O `.env` do agente na máquina do Leonardo **já aponta para produção** desde
05/08 e está funcionando — `reanalisar.py --listar` conectou.

## O que entrou em produção em 04/08

**Agente (`master`)**

- `ec02c69` — o agente parou de fingir que sabe se há sessão no eProc, TRF6 e
  RUPE. Esses três entraram em `SEM_DETECCAO_DE_LOGIN` e agora são tentados 4
  vezes: uma imediata e três espaçadas de 5 minutos. Quem decide se havia sessão
  é o extrator. `_processar_sistema` devolve `False` quando falha no primeiro CNJ
  (ninguém logou) e `True` quando a sessão cai no meio. A pausa antiga de 30s
  saiu — não dava para logar em nada nesse tempo.
- `1925599` — `pausar-agente.bat` e `voltar-agente.bat`. Enquanto existir
  `AGENTE-PAUSADO.txt` na pasta, o agente ignora comandos novos. Sobrevive a
  reinício do Windows e está no `.gitignore`.

**Painel (`main`)**

- `c8a5f69` — motivo do erro aparece embaixo da linha (vermelho para erro, âmbar
  para pendente) e nova coluna Sistema entre Observações e Aprovação.
- `b09d79e` — motivo alinhado à direita, nascendo embaixo da coluna Status.
- `dfb696f` — rodada parada há mais de 90 min deixa de bloquear o botão Iniciar
  (mesmo critério do agente), e o painel passou a mostrar o motivo da recusa em
  vez de engolir o 409 em silêncio.

## O que já foi provado

A correção do login está **validada nos três sistemas**:

- 03/08 12:50 — clicou 12:50:55, primeiro processo salvo 12:59:30. Os **15
  processos do eProc** saíram. Era o sistema que nunca conseguia.
- 04/08 14:29 — **RUPE** e **TRF6** extraíram.
- Nenhum processo devolvido por sessão caída desde então.

Com a pausa antiga de 30 segundos, a rodada de 03/08 teria falhado igual à de
02/08.

## Estado da fila em 05/08

141 processado · 16 pendente · 4 erro_browser · 3 ignorado

Últimas rodadas: 15+3 (03/08), 8+2 e 2+4 (04/08).

## O que fazer em seguida

### 1. Gerar os rascunhos que faltam (não precisa de login)

Três processos estão `processado` mas sem rascunho. Os documentos já estão no
banco, então o `reanalisar.py` resolve sem abrir navegador:

| Processo | Docs | Sistema |
|---|---|---|
| `5010416-09.2024.8.13.0439` | 81 | pje |
| `1000112-48.2026.8.13.0439` | 13 | eproc_tjmg |
| `1002686-44.2026.8.13.0439` | 6 | eproc_tjmg |

Conferir a lista com `python reanalisar.py --listar` e então rodar a reanálise.
**Esse script nunca foi executado** — rodar um processo primeiro e conferir o
rascunho no painel antes de fazer os três.

### 2. Conferir os 4 processos com erro (precisa abrir no site)

Nenhum é erro de login. Todos são "não achei o processo". A checagem é abrir
cada um no navegador e ver se aparece:

| Processo | Onde | Detalhe |
|---|---|---|
| `2812197-72.2026.8.13.0000` | RUPE | 9ª Câmara Cível — Banco Mercantil × Maria Inez |
| `5004160-55.2023.8.13.0384` | RUPE | 21ª Câmara Cível |
| `5009543-77.2022.8.13.0439` | PJe | 1ª Vara Cível de Muriaé — polo ativo em SIGILO |
| `5005158-86.2024.8.13.0384` | PJe | 1ª Vara Cível de Leopoldina — abriu com **zero** documentos |

Hipótese para todos: o processo existe, mas não aparece para o login do
Henrique (sem procuração cadastrada, segredo de justiça ou processo arquivado).
O de Muriaé estar marcado como SIGILO reforça isso.

### 3. Rodar uma extração na máquina do Leonardo

Depende de logar no PJe, eProc e RUPE com as credenciais do Henrique. O eProc e
o RUPE exigem código temporário que chega no e-mail dele — ele se dispôs a
repassar cerca de 2 vezes por dia, então combinar horário.

Antes de rodar: garantir que o agente da máquina do Henrique não vai disputar a
fila. Com o computador dele desligado não há risco (foi o combinado). Se ficar
ligado, ele precisa rodar `atualizar.bat` e depois `pausar-agente.bat`.

**O que medir:** quanto tempo o Henrique leva para logar no eProc e no RUPE,
contando a ida ao e-mail. Os 5 minutos de `ESPERA_LOGIN_S` foram estimativa, sem
nenhuma medição.

## Pendências conhecidas

- **A cura da detecção de login** — o que está no ar é margem, não cura. O
  caminho está em `docs/deteccao-de-login-correcao-definitiva.md`, incluindo uma
  pista barata ainda não explorada: o CDP `/json` já devolve o `title` de cada
  aba, sem Playwright.
- **3 CNJs começando com 0** ficam `ignorado` porque nem a skill nem o
  `cnj_router.py` sabem o sistema: `0085924-27.2016.8.13.0439`,
  `0091559-86.2016.8.13.0439`, `0154582-16.2010.8.13.0439`. Perguntar ao Henrique
  em que site ele abre esses.
- **`6003123-67.2026.4.06.3821` (TRF6)** está `pendente` com um motivo velho, mas
  tem 3 documentos e 3 rascunhos salvos. Não é erro: o agente morreu antes de
  carimbar. Deve virar `processado` sozinho na próxima rodada.
- **59 processos concluídos carregam motivo de erro antigo** ("Erro durante
  processamento", "Sistema indisponível ou timeout de login"), todos anteriores a
  01/08. É resíduo de antes de o agente gravar o erro real — não acontece mais, e
  o painel já esconde. Limpeza cosmética, o Leonardo decidiu não fazer.
- **Branch `wip/copia-local-antiga`** no repo do painel guarda o trabalho local
  antigo do Leonardo. O único item útil dela já foi refeito e está em produção.

## Como rodar

```bash
cd ~/Projects/paes-alves-pequeno-advogados/controladoria-playwright
venv\Scripts\python.exe reanalisar.py --listar
```

Testes do agente, antes e depois de qualquer mudança — 38 no total:

```bash
venv\Scripts\python.exe test_runner.py
venv\Scripts\python.exe test_sistema_auth.py
venv\Scripts\python.exe test_agente.py
```

## Hipóteses já descartadas — não reabrir

Chrome duplicado ou perfil errado · rótulo `pje_2g` vs `pje_tjmg_2inst` (o
roteador trata igual) · troca de modelo na skill do Cowork · Avast bloqueando o
Playwright (era o Chrome entupido de abas, corrigido em `6b58edc`) · RUPE não
achar números começando com 5 · sessão do eProc/RUPE caindo em segundos ·
falso negativo no `verificar_sessao` do extrator.
