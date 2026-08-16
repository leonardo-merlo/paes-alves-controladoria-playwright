# Handoff — 2026-08-16: separar login da extração + cards de erro no painel

Ponto de partida para uma sessão nova. Os dias 14 e 15/08 foram de caça a bug na
máquina do Henrique; está tudo corrigido e no ar. O que vem agora é trabalho novo.

## Onde está cada coisa

- **Agente (Python):** `~/Projects/paes-alves-pequeno-advogados/controladoria-playwright`
  — branch `master`. Roda na máquina do Henrique.
- **Painel (Next.js/Vercel):** `~/Projects/paes-alves-pequeno-advogados/paes-alves-controladoria`
  — repo no GitHub é `ia-controladoria-advocacia`, branch `main`.
- **Máquina do Henrique:** `C:\Users\Acer\...\SISTEMA`. Atualiza com `atualizar.bat`.
- **Supabase produção:** as chaves estão no `.env` do repo do agente.

## Estado atual (16/08)

61 de 67 processos extraídos com rascunho. Sobraram 4 erros, todos explicados:
3 pedem certificado digital e 1 é o TRF1, que não tem extrator.

O fluxo roda de ponta a ponta. Não está quebrado — o que falta é melhorar.

## O que foi corrigido em 14-15/08 (não reabrir)

- **`c029469`** — dois Chrome na porta 9222 sobem os dois, um em `127.0.0.1` e
  outro em `::1`. Como `localhost` resolve para os dois, qual deles o agente
  achava era sorteio. `CDP_URL` agora é fixo em `127.0.0.1`, o `iniciar.py` abre
  aba via CDP em vez de subir um segundo Chrome, e `/json/new` usa PUT (exige PUT
  desde o Chrome 111; era GET e voltava 405 calado).
- **`c029469`** — `"Nenhuma aba"` passou a contar como login pendente: a fila
  volta para `pendente` em vez de queimar em `erro_browser`.
- **`d6dfc75`** — erro de rede repetido não vira mais parede de texto na janela.
- **`2f70b9f`** — o número do processo manda no tribunal; o rótulo vindo do
  e-mail só escolhe o sistema dentro dele.

## Tarefas

### 1. Separar "abrir sistemas" de "iniciar extração"

Hoje um clique só abre o Chrome, espera o login e extrai. Os sistemas sem
detecção de login (eProc, TRF6, RUPE) são tentados **imediatamente**, falham
porque ninguém logou ainda, e gastam 1 das 4 tentativas. Em 15/08 o RUPE gastou
as 4 e foi pulado a rodada inteira.

Separado vira: **abre → loga com calma → roda.** Some a máquina de retentativa.

**Lado Python (baixa complexidade, quase tudo existe):**
- `iniciar.py` `main()` já é dois blocos colados: "abre Chrome e abas" e depois
  `modo_supabase(modo_auto=True)`. É um corte limpo.
- `runner.modo_supabase(modo_auto=False)` já é o caminho "logins prontos, vai
  direto". **Porém** ele chama `preparar_autenticacao(modo_auto=False)`, que faz
  `input()` esperando Enter no terminal — isso não serve para o agente. Precisa
  de um terceiro modo: "assume logado, segue".
- `agente.py` precisa ramificar em `comando['acao']`.
- `comandos.acao` **não tem CHECK constraint** — ação nova sem migração.

Fazer de forma **aditiva**: a ação `iniciar` atual continua funcionando. Assim o
painel pode virar a chave depois, sem risco para o Henrique.

### 2. Começar a extração pelo RUPE

Observação do Leonardo, e é boa: a sessão do RUPE cai mais rápido que a dos
outros. Como ele é o primeiro a ser logado e o último a ser usado, é o que mais
tempo passa parado.

Hoje a ordem vem de `sistemas_necessarios = list(por_sistema.keys())`, que segue
`data_entrada` — ou seja, é acidental. Ordenar com `pje_tjmg_2inst` na frente.

Com a tarefa 1 feita isso importa ainda mais: todos os logins acontecem antes,
então a sessão mais frágil deve ser gasta primeiro.

### 3. Painel — card de motivos de erro

Hoje existem os cards "qualidade da análise" e "motivos de mudança"
(`app/dashboard/QualidadeAnalise.tsx`, `app/dashboard/qualidade.ts`).

Colocar os dois mais um terceiro, **um terço da largura cada**: "motivos de erro".

Conteúdo: ranking por frequência, mais repetido no topo. As categorias que já
existem no banco hoje, em `processos.motivo_ignorado`:

- `Sistema não implementado`
- `PJe recusou o acesso: ... mediante login com certificado digital`
- `não localizado no RUPE (nenhum resultado na pesquisa)`
- `Tabela de eventos não encontrada ... processo não localizado ou sessão expirada`

Agrupar por categoria, não pelo texto cru — as mensagens trazem o número do CNJ
no meio e nunca colidiriam.

### 4. Sugerir o sistema provável quando não encontra

Quando um processo não é encontrado, dizer no painel qual sistema ele parece ser
pelo número.

**Isso é quase de graça:** o `cnj_router.rotear(cnj)` **sem** o hint já devolve o
sistema derivado do CNJ. Basta comparar com o sistema em que foi procurado e
mostrar quando divergirem — ou dizer "pelo número parece TRF1, que não tem
extrator".

## Gotchas da máquina do Henrique

- **Python 3.14** (`C:\Users\Acer\AppData\Local\Python\pythoncore-3.14-64`),
  enquanto a do Leonardo tem 3.13.7. Cospe `ValueError: I/O operation on closed
  pipe` do asyncio a cada CNJ. **Decisão de 16/08: não mexer** — está funcionando,
  e trocar Python tem risco de derrubar o ambiente. Só revisitar se o Chrome
  voltar a cair com frequência.
- **Um Chrome só na 9222.** Perfil único: `C:\ChromeControladoria`. Se aparecer
  mais de uma linha em `Get-NetTCPConnection -LocalPort 9222 -State Listen`, tem
  Chrome duplicado.
- **Crédito da API Anthropic.** Zerou no meio da rodada de 15/08 e 12 processos
  foram salvos sem análise (a varredura recuperou depois, sozinha). Falha
  silenciosa: o painel mostra "processado" e o rascunho não existe. O Leonardo ia
  configurar recarga automática no Console.
- **Certificado digital.** 3 processos precisam. O sistema nunca faz login — usa
  a sessão que o Henrique abriu na mão —, então basta ele entrar no PJe com o
  certificado no Chrome da extração. Possível tropeço: o perfil da extração é
  separado e pode faltar a extensão do assinador. **Adiado por decisão do
  Leonardo em 16/08** — hoje o erro já avisa o motivo exato, que é o suficiente.

## Como conferir o estado sem o MCP do Supabase

O MCP caiu algumas vezes. Dá para consultar direto com o venv do repo:

```python
import sys
sys.path.insert(0, r"C:\Users\User\Projects\paes-alves-pequeno-advogados\controladoria-playwright")
from supabase_writer import _get_client, _carregar_env
_carregar_env(); c = _get_client()
print(c.table("processos").select("pje_status").execute().data)
```

## Testes

```bash
venv\Scripts\python.exe test_cnj_router.py
venv\Scripts\python.exe test_runner.py
venv\Scripts\python.exe test_sistema_auth.py
venv\Scripts\python.exe test_agente.py
```

## Hipóteses já medidas — não reabrir

- "A segunda instância do Chrome não consegue subir a porta" — **falso**, medido
  em 14/08: as duas sobem, em pilhas diferentes.
- "O PC do Henrique dormiu e derrubou a rodada" — **falso**, medido em 15/08: o
  agente gravou no banco 3 minutos depois do último documento.
- "Foi o Henrique que esqueceu de atualizar" — **falso**: o `master` não tinha
  nada novo naquele momento.
