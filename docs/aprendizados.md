# Aprendizados

Registro do que a gente descobre investigando incidentes reais — não é plano,
não é dívida técnica (isso fica em `divida-tecnica.md`), é "isto aconteceu,
isto foi o motivo real, é bom lembrar disso da próxima vez". Entradas por data,
mais recente primeiro. Nunca reescreve entrada antiga — só acrescenta.

---

## 08/09/2026 — o dia dos três avisos otimistas

Numa rodada só, três etapas diferentes falharam e, nas três, a mensagem que
chegou até o Leonardo/Henrique disse que tinha dado certo. Padrão que vale
vigiar em qualquer coisa nova: **uma etapa que só avisa quando falha, e fica
muda quando o "avisar" em si falha, sempre mente por omissão.**

1. **"Abrir sistemas" travou sem escrever nada.** A primeira chamada que essa
   ação faz — perguntar ao banco quais processos estão pendentes — não tinha
   limite de tempo. Uma rede engasgada ali prendia a função inteira, sem
   exceção pra cair no bloco de erro. Corrigido: teto de 3 minutos
   (`TIMEOUT_ABRIR_SISTEMAS_S`, `agente.py`).

2. **Chrome caiu no meio da extração — e o resumo culpou o login.** O circuito
   de segurança que aborta a rodada quando o Chrome para de responder
   funcionou certinho, gravou o motivo certo em cada processo devolvido. O
   problema era só a frase-resumo do topo: ela só reconhece uma lista fixa de
   causas conhecidas, e "Chrome parou de responder" não estava nessa lista —
   então caiu no texto genérico "Login não concluído? Verifique", que é a
   causa errada e manda a pessoa checar justamente o que estava certo.

3. **eProc TJMG "não estava aberto" — mas a aba nunca foi confirmada.**
   "Abrir sistemas" listou "Abri eProc TJMG" no resumo, mas essa lista é
   montada a partir de QUEM PRECISAVA ser aberto, não de quem de fato abriu.
   O pedido HTTP que abre a aba tem 5s de prazo e pode falhar silenciosamente
   — só um aviso no terminal que ninguém vê. 24 minutos depois, quando a
   extração tentou usar aquela aba, não achou nenhuma — e a falha inteira do
   sistema (35 processos) aconteceu em menos de 1 segundo, sinal forte de que
   a aba nunca chegou a existir, não de que sumiu no meio do caminho.

**Fio comum:** nas três, o código sabia a verdade internamente (o motivo certo
estava gravado por processo, no caso 2) ou tinha como saber e não checou (casos
1 e 3). O consertos pontuais (timeout, mensagem melhor) resolvem o sintoma de
cada um. A causa de fundo — falta de confirmação depois de cada ação, e
mensagens-resumo otimistas por padrão — é maior que os três juntos. Ver
`docs/fluxo-extracao-passo-a-passo.md` para o mapa completo de onde isso ainda
acontece.

**Achado à parte, não-bug:** o RUPE levou 26 minutos para 6 processos nessa
mesma rodada. Não é regressão — já é comportamento conhecido e documentado
(`divida-tecnica.md`, item do CNJ que sozinho levou 14 min). O sistema
simplesmente é lento.

**Achado à parte, explica um "estranho":** a regra que decide "sessão
envelheceu esperando a vez" mede o tempo desde que a RODADA DE EXTRAÇÃO
começou — não desde que a pessoa efetivamente logou. Numa noite com mais de
uma tentativa (uma rodada fracassada, depois outra), o login pode ter
acontecido bem antes da rodada que finalmente rodou, fazendo a sessão parecer
mais "nova" do que realmente estava. Isso pode (ainda não confirmado) explicar
por que o PJe expirou aos 22 minutos quando historicamente aguentava 40+.
