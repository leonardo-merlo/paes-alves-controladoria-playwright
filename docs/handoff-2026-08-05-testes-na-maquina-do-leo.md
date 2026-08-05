# Handoff — Controladoria (2026-08-05, atualizado no fim do dia)

Ponto de partida para uma sessão nova. O Henrique viaja e volta na segunda; até
lá os testes rodam na máquina do Leonardo. **Os testes de 05/08 já aconteceram** —
este documento foi reescrito com o resultado.

## Onde está cada coisa

- **Agente (Python):** `~/Projects/paes-alves-pequeno-advogados/controladoria-playwright`
  — repo `paes-alves-controladoria-playwright`, branch `master`.
- **Painel (Next.js/Vercel):** `~/Projects/paes-alves-pequeno-advogados/paes-alves-controladoria`
  — atenção, o repo no GitHub chama `ia-controladoria-advocacia`, branch `main`.
- **Supabase produção:** `hjesbvnxeivphplfymml`.
- **Máquina do Henrique:** `C:\Users\Acer\OneDrive\Desktop\SISTEMA`. Atualiza com
  `atualizar.bat` (faz fetch, reset e reinicia o agente sozinho).
- **Para rodar na máquina do Leonardo:** duplo clique em `agente-watchdog.bat` —
  ele abre o Chrome de extração (perfil próprio `C:\ChromeControladoria`) **e** o
  agente, numa janela só. Não use o `iniciar-chrome-debug.bat`: ele abre o Chrome
  com o perfil normal e, se já houver Chrome aberto, a porta de debug não sobe e o
  agente fica cego.

## O que entrou em produção em 04/08

**Agente (`master`)**

- `ec02c69` — o agente parou de fingir que sabe se há sessão no eProc, TRF6 e
  RUPE. Esses três entraram em `SEM_DETECCAO_DE_LOGIN` e agora são tentados 4
  vezes: uma imediata e três espaçadas de 5 minutos. Quem decide se havia sessão
  é o extrator.
- `1925599` — `pausar-agente.bat` e `voltar-agente.bat`. **Só funciona em cópia
  atualizada** — agente antigo ignora o arquivo de pausa. Numa máquina não
  atualizada, fechar a janela preta é o jeito confiável de parar.

**Painel (`main`)** — `c8a5f69`, `b09d79e`, `dfb696f`: motivo do erro visível,
coluna Sistema, e rodada parada há mais de 90 min deixa de bloquear o Iniciar.

## O que entrou em produção em 05/08

Commit `9542ed0`, três correções, todas provadas contra os sistemas reais.

**1. RUPE — achar recurso vindo da 1ª instância.** A busca começava em
`processos.rupe?acao=0&localizacaoAtual=862`. Esse filtro prende a pesquisa à caixa
"Meus Processos", e recurso que subiu da 1ª instância não está nela. Medido nos
dois caminhos, com controle:

| CNJ | com o filtro | sem o filtro |
|---|---|---|
| `5004160-55.2023.8.13.0384` (origem 0384) | não acha | acha — idProcesso 7418699 |
| `5003155-90.2024.8.13.0439` (origem 0439) | não acha | acha — idProcesso 6849292 |
| `0145032-91.2026.8.13.0000` (origem 0000) | acha | acha |

`MEUS_PROCESSOS` virou `CONSULTA_PROCESSOS`, sem query string.

**2. PJe — dizer o motivo real da recusa.** O PJe recusa acesso por caixa de alerta
do navegador. Sem ouvinte, o Playwright fechava a caixa sozinho e a recusa ficava
invisível: o processo virava "0 documentos", motivo errado para quem lê o painel.
Agora o texto do alerta vira o motivo, e recusa de acesso entrou na lista de erros
permanentes (insistir 3 vezes num "sem permissão" só repetia o alerta).

**3. Varredura de análise perdida.** Ao fim de cada rodada o agente procura quem
ficou `processado` sem rascunho e reanalisa a partir dos documentos já salvos —
sem navegador e sem login. O painel passa a dizer "N análise(s) recuperada(s)".

40 testes passando (eram 38).

## O que foi provado em 05/08

**Rodada das 15:41 — extração completa, os quatro sistemas.** 14 processados, 1 sem
novidade, 5 com erro, em 25min39. Todos os sistemas entraram na **tentativa 1/4**,
porque o Leonardo logou **antes** de clicar em Iniciar. Essa é a ordem certa: o
agente só tenta 4 vezes (0, 5, 10 e 15 min) e depois desiste — logar antes garante
que a primeira tentativa aproveite o código temporário.

**Rodada das 18:07 — validação das três correções.** 2 processados, 3 com erro,
1 análise recuperada, em 12 minutos:

- RUPE: `5004160-55` extraiu **84 documentos**, `5003155-90` extraiu **72**. Os dois
  eram "não localizado" antes.
- PJe: `5005158-86` passou a registrar *"PJe recusou o acesso: ...certificado
  digital"*.
- Varredura: o rascunho do `1002854-46` foi apagado de propósito antes da rodada e
  voltou sozinho no fim — analisando 11 documentos contra 1 do original, e chegando
  ao mesmo veredito.

**A sessão do RUPE caiu por ociosidade** entre uma rodada e outra (~30 min parada),
e o agente reportou `sessao_expirada` corretamente, devolvendo a fila. Numa rodada
longa isso pode acontecer no meio — ver pendências.

## Estado da fila em 05/08, fim do dia

158 processado · 3 erro_browser · 3 ignorado · **0 pendente** · 0 processado sem rascunho

Os 3 em erro são todos legítimos, cada um com o motivo verdadeiro:

| Processo | Onde | Motivo |
|---|---|---|
| `2812197-72.2026.8.13.0000` | RUPE | não existe na busca — confirmado também na mão |
| `5009543-77.2022.8.13.0439` | PJe | não existe na busca — confirmado também na mão |
| `5005158-86.2024.8.13.0384` | PJe | existe, mas exige certificado digital |

## Decisões pendentes com o Henrique — não mexer antes da resposta

- **Processo não encontrado:** continua `erro_browser` com o motivo, ou vira
  `processado` com a explicação? Hoje é a primeira opção.
- **Processo com 2 registros no RUPE:** o `5003155-90` tem apelação (sequencial 1) e
  embargos de declaração (sequencial 2). O extrator pega a primeira lupa que
  encontra e não sabe que existe a segunda. Ler os dois? Priorizar um? Qual?
- **3 CNJs começando com 0** ficam `ignorado` porque nem a skill nem o
  `cnj_router.py` sabem o sistema: `0085924-27.2016.8.13.0439`,
  `0091559-86.2016.8.13.0439`, `0154582-16.2010.8.13.0439`. Em que site ele abre
  esses?

## Pendências técnicas

- **Prevenir o "processado sem rascunho" na origem.** A varredura conserta depois;
  a causa segue de pé. Quando o agente morre no meio, o processo fica com documentos
  salvos e ainda na fila; na rodada seguinte a extração incremental não acha
  documento novo, conclui "nada novo" e carimba `processado` — **antes de a análise
  ser chamada**. O atalho de "nada novo" (`eh_nada_novo`, `runner.py`) só deveria
  valer para quem já tem rascunho. Existe precedente no próprio arquivo:
  `ids_com_documentos` foi escrito contra o gêmeo desse problema.
- **Botão Iniciar reaparece no painel com a rodada em andamento.** Visto às 18:12
  com rodada de 5 minutos; a regra deveria só liberar após 90 min. Ou a regra não
  pega, ou o botão aparece habilitado e só a API recusa — experiência ruim. É no
  repo do painel.
- **Sessão do RUPE morre por ociosidade** (~30 min). Numa rodada longa pode cair no
  meio. Ideia não testada: o agente tocar a aba de tempos em tempos para mantê-la
  viva.
- **A cura da detecção de login** — o que está no ar é margem, não cura. O caminho
  está em `docs/deteccao-de-login-correcao-definitiva.md`. **Pista confirmada em
  05/08:** o CDP `/json` devolve o `title` de cada aba sem Playwright, e o título
  distingue logado de deslogado — o eProc mostra "Painel do Advogado" só quando há
  sessão. O RUPE é o único ambíguo pelo título.
- **Rascunho de processo grande** — o analyzer manda no máximo 7 documentos na
  íntegra (`MAX_DOCS_PARA_ANALISE`), mais até 30 referenciados só pelo título. Num
  processo de 84 peças a IA não leu tudo. Se a conclusão não bater com a realidade,
  o recorte de 7 é o suspeito.
- **59 processos concluídos carregam motivo de erro antigo**, todos anteriores a
  01/08. Resíduo de antes de o agente gravar o erro real; o painel já esconde.
  Limpeza cosmética, o Leonardo decidiu não fazer.

## Para olhar no painel

Dois rascunhos saíram como **risco CRÍTICO com status AGUARDAR e sem prazo**, que é
uma combinação estranha: `5007669-52.2025.8.13.0439` e `5004160-55.2023.8.13.0384`.
Ou a IA viu algo grave que não gera prazo agora, ou está inflando o risco. Precisa
de olho jurídico.

E o mais urgente da rodada da tarde: `6002718-31.2026.4.06.3821` — MANIFESTAR,
Henrique, **1 dia útil**.

## Como rodar

```bash
cd ~/Projects/paes-alves-pequeno-advogados/controladoria-playwright
venv\Scripts\python.exe reanalisar.py --listar
```

Testes do agente, antes e depois de qualquer mudança — 40 no total:

```bash
venv\Scripts\python.exe test_runner.py
venv\Scripts\python.exe test_sistema_auth.py
venv\Scripts\python.exe test_agente.py
```

## Hipóteses já descartadas — não reabrir

Chrome duplicado ou perfil errado · rótulo `pje_2g` vs `pje_tjmg_2inst` (o
roteador trata igual) · troca de modelo na skill do Cowork · Avast bloqueando o
Playwright (era o Chrome entupido de abas, corrigido em `6b58edc`) · sessão do
eProc/RUPE caindo em segundos · falso negativo no `verificar_sessao` do extrator.

> **Correção de 05/08:** a lista acima trazia "RUPE não achar números começando com
> 5". **Aquela hipótese estava certa** e havia sido descartada sem medição — era o
> filtro `localizacaoAtual=862`. Foi removida daqui. Lição: hipótese descartada sem
> teste não é hipótese descartada.
