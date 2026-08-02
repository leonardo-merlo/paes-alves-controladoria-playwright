# Detecção de login — a correção definitiva (pendente)

O que está no código hoje (tentativas espaçadas em `sistema_auth.py`) é uma
**margem, não a cura**. Este documento existe para que a cura não se perca.

## O problema de fundo

O agente não sabe se há sessão ativa no eProc, no TRF6 e no RUPE. Nesses sistemas
a tela de login mora no **mesmo endereço** da tela interna, e o agente só lê o
endereço da aba. O PJe escapa porque, deslogado, redireciona para `login.seam`.

Isso quebrou a produção em 02/08/2026: o agente deu eProc e RUPE como logados no
instante zero, extraiu 30 segundos depois — antes de o Henrique logar — e devolveu
17 processos à fila com `sessao_expirada`. O PJe, na mesma rodada, funcionou.

A solução atual tenta 4 vezes — uma imediata e três espaçadas de 5 minutos. Ela
cobre o caso normal, mas o agente continua **adivinhando**. Se um dia o login
demorar mais que a última tentativa, o mesmo dia se repete.

O espaçamento é de 5 minutos porque o login do eProc e do RUPE exige um código
temporário que chega por e-mail: o Henrique precisa sair da tela, abrir a caixa de
entrada e voltar. Como `verificar_sessao` do RUPE recarrega a aba, uma tentativa
apressada apaga justamente o código que ele está colando.

## A cura

Ler a tela e verificar se há campo de senha. Página pedindo senha = não logado,
por mais que o endereço pareça o de dentro.

**As peças já existem e estão testadas**, em `sistema_auth.py`:

- `_tem_campo_de_senha(campos)` — recebe os campos visíveis da página e diz se é
  tela de login. Já cobre a armadilha do eProc, que exibe a senha como
  `type="text"` com id `pwdSenha` e esconde o campo password real com 0x0 atrás.
- `_avaliar_login(url, sistema, tem_form_login)` — o parâmetro `tem_form_login` é
  justamente o sinal que falta. Hoje é sempre `False`.
- `test_sistema_auth.py` guarda o formato real das telas de login e de sessão
  logada dos três sistemas, capturado ao vivo e validado nos dois sentidos.

**Falta uma única coisa:** ler os campos da página sem Playwright.

## Por que sem Playwright

Já foi tentado ler o DOM das abas com Playwright neste ponto do código. Na máquina
do Henrique a leitura falhou e o agente morreu com código -1 no meio do primeiro
CNJ — o Playwright do extrator não sobrevive a uma segunda instância aberta e
fechada nesse caminho. O aviso está na docstring de `verificar_autenticacoes`.

Ressalva: isso foi observado enquanto o Chrome estava entupido de abas, bug
corrigido depois em `6b58edc`. **Pode ter sido consequência, não causa.** Vale
reavaliar — com cuidado, e só com o Henrique disponível para testar.

## Caminho não explorado (o mais barato)

O endpoint CDP `http://localhost:9222/json`, que o agente **já consulta** em
`_get_abas_chrome()`, devolve para cada aba não só a `url` como também o
**`title`**. Sem Playwright, sem dependência nova, sem risco de derrubar o agente.

Se o título da tela de login do eProc e do RUPE for diferente do título da tela
interna, ele é o sinal que falta — e a correção vira uma linha.

**O que falta para decidir:** capturar os títulos reais na máquina do Henrique,
nos dois estados (deslogado e logado), nos três sistemas. É o mesmo tipo de
captura que já foi feita para os campos de senha e está em `test_sistema_auth.py`.

## Dado que também falta

Quanto tempo o Henrique leva para logar no eProc e no RUPE, contando a ida ao
e-mail para buscar o código. `ESPERA_LOGIN_S` foi escolhido sem nenhuma medição —
5 minutos é estimativa, não dado. Pedir a ele que cronometre numa rodada real.

Com a cura implementada, esse número deixa de importar: o agente passa a saber a
hora certa em vez de esperar.
