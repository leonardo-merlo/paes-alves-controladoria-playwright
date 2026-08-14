"""
sistema_auth.py — Detecta autenticação por sistema e abre abas no Chrome via CDP.
"""

import asyncio
import json
import re
import urllib.request
import urllib.parse
from typing import Callable, Awaitable

# 127.0.0.1 e não "localhost", de propósito. `localhost` resolve para ::1 E para
# 127.0.0.1, e quando existem dois Chrome na 9222 cada um fica com uma pilha: o
# primeiro pega 127.0.0.1, o segundo sobra com ::1. Aí quem responde depende de
# qual endereço o cliente escolher — medido em 14/08 nesta máquina, urllib e
# Playwright foram os dois para ::1 e falaram com o Chrome errado. Fixar o IPv4
# faz o agente sempre falar com o primeiro Chrome, que é o do watchdog.
CDP_URL = "http://127.0.0.1:9222"

# Caminho do Chrome e perfil ÚNICO da extração. Mora aqui porque iniciar.py,
# preparar.py e o agente-watchdog.bat precisam concordar: perfis diferentes na
# mesma porta significam que o segundo Chrome não sobe o CDP e suas abas ficam
# invisíveis para o agente — foi o que quebrou a rodada de 14/08.
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_PROFILE = r"C:\ChromeControladoria"
CDP_PORT = 9222

# URL base de cada sistema para abrir no Chrome
SISTEMA_URLS = {
    "pje_tjmg":       "https://pje.tjmg.jus.br/pje/Processo/ConsultaProcesso/listView.seam",
    "eproc_tjmg":     "https://eproc1g.tjmg.jus.br/eproc/",
    "pje_tjmg_2inst": "https://pe.tjmg.jus.br/rupe/portaljus/intranet/principal.rupe",
    "pje_tjrj":       "https://tjrj.pje.jus.br/",
    "eproc_trf2":     "https://eproc.trf2.jus.br/",
    "eproc_trf6":     "https://eproc1g.trf6.jus.br/eproc/",   # JFMG — 1ª instância federal
    "eproc_trf6_2g":  "https://eproc2g.trf6.jus.br/eproc/",   # TRF6 — 2ª instância federal
}

# Host esperado na URL quando a sessão está ativa
SISTEMA_HOST = {
    "pje_tjmg":       "pje.tjmg.jus.br",
    "eproc_tjmg":     "eproc1g.tjmg.jus.br",
    "pje_tjmg_2inst": "pe.tjmg.jus.br",
    "pje_tjrj":       "tjrj.pje.jus.br",
    "eproc_trf2":     "eproc.trf2.jus.br",
    "eproc_trf6":     "eproc1g.trf6.jus.br",    # JFMG — 1ª instância
    "eproc_trf6_2g":  "eproc2g.trf6.jus.br",    # TRF6 — 2ª instância
}

# Fragmentos de URL que indicam sessão encerrada ou tela de login
INDICADORES_DESLOGADO = ["/login", "/Login", "login.seam", "token_invalid",
                         "sessao_expirada", "externo_controlador"]

# Sistemas cuja tela de login mora no MESMO endereço da tela interna: pelo
# endereço não há como distinguir logado de deslogado. Olhar só a URL os dava como
# logados no instante zero, e o agente extraía antes de o Henrique logar — em
# 02/08/2026 isso queimou a fila inteira do eProc (15) e do RUPE (2) no primeiro
# CNJ, com o Henrique logando enquanto o agente já tinha desistido.
# Para estes não existe sinal de login para esperar: o agente tenta de tempos em
# tempos e deixa o extrator, que sabe ler a tela, dizer se havia sessão.
# O PJe fica de fora porque deslogado ele redireciona para login.seam — ali a
# leitura do endereço funciona, e é por isso que o PJe nunca falhou assim.
SEM_DETECCAO_DE_LOGIN = {"eproc_tjmg", "eproc_trf6", "eproc_trf6_2g", "pje_tjmg_2inst"}

# Quanto tempo o Henrique tem para logar entre uma tentativa e outra, e quantas
# tentativas até desistir. Contando a tentativa imediata (ver deve_tentar), as
# quatro caem em: 0, 5, 10 e 15 minutos.
#
# O espaçamento é largo de propósito, por dois motivos. O login do eProc e do RUPE
# exige um código temporário que chega por e-mail — ninguém conclui isso em um
# minuto. E verificar_sessao do RUPE recarrega a aba: tentar com frequência
# apagaria justamente o código que ele estivesse colando.
ESPERA_LOGIN_S = 300
MAX_TENTATIVAS_LOGIN = 4


def _get_abas_chrome() -> list[dict]:
    """Lista as abas abertas no Chrome via CDP HTTP — sem Playwright, sem Avast."""
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json", timeout=2) as resp:
            return json.loads(resp.read())
    except Exception:
        return []


# ── peças da checagem boa, ainda sem uso ──────────────────────────
# Campo de senha visível = a página ainda está pedindo login, por mais que o
# endereço pareça o de dentro do sistema. É a cura para o eProc, o TRF6 e o RUPE,
# que por endereço nenhum são distinguíveis (ver SEM_DETECCAO_DE_LOGIN). A
# tentativa espaçada que está no ar hoje é margem, não cura.
# Falta a parte difícil: ler os campos da página sem Playwright (ver o aviso em
# verificar_autenticacoes). Enquanto isso não existe, isto fica aqui coberto por
# teste, pronto para ser ligado — o caminho está em
# docs/deteccao-de-login-correcao-definitiva.md.
#
# Procurar só por type="password" não basta: o eProc TJMG exibe a caixa de senha
# como type="text" com id "pwdSenha" e mantém o campo password real com 0x0 atrás
# dela. Quem olha só o type conclui que não há formulário.
RE_CAMPO_SENHA = re.compile(r"senha|password|pwd", re.IGNORECASE)


def _tem_campo_de_senha(campos: list[dict]) -> bool:
    """A página está pedindo senha? Recebe os campos visíveis lidos da página."""
    for campo in campos:
        if campo.get("type") == "password":
            return True
        if RE_CAMPO_SENHA.search(f"{campo.get('id') or ''} {campo.get('name') or ''}"):
            return True
    return False


def _avaliar_login(url: str, sistema: str, tem_form_login: bool) -> bool:
    """Decide se a aba representa uma sessão ativa. Função pura — ver test_sistema_auth.py."""
    host = SISTEMA_HOST.get(sistema, "")
    if not host or host not in url:
        return False
    if any(ind in url for ind in INDICADORES_DESLOGADO):
        return False
    return not tem_form_login


def deve_tentar(
    sistema: str,
    detectado_logado: bool,
    segundos_desde_a_ultima: float,
    tentativas_feitas: int,
) -> bool:
    """
    Chegou a hora de tentar extrair este sistema? Função pura — ver test_sistema_auth.py.

    Sistema com detecção confiável (PJe): tenta assim que o login aparece no
    endereço. Sistema sem detecção: não existe sinal para esperar, então tenta
    quando o tempo de login se esgota. Nos dois casos vale o teto de tentativas e
    o intervalo mínimo entre elas — sem o intervalo, um sistema dado como logado
    mas com a sessão caída seria tentado de 3 em 3 segundos até o timeout.
    """
    if tentativas_feitas >= MAX_TENTATIVAS_LOGIN:
        return False
    if tentativas_feitas > 0 and segundos_desde_a_ultima < ESPERA_LOGIN_S:
        return False
    if sistema in SEM_DETECCAO_DE_LOGIN:
        # a primeira é imediata: se a sessão já estava de pé (Chrome aberto desde
        # a rodada anterior), extrai na hora em vez de cobrar espera de quem não
        # precisa. Custa segundos e acontece antes de o usuário começar a digitar.
        return tentativas_feitas == 0 or segundos_desde_a_ultima >= ESPERA_LOGIN_S
    return detectado_logado


def _esgotou_as_tentativas(
    sistemas: list[str], processados: set[str], tentativas: dict[str, int]
) -> bool:
    """
    Todo mundo que falta já gastou as tentativas? Serve para encerrar a espera sem
    ficar parado até o timeout quando não há mais o que tentar.
    Função pura — ver test_sistema_auth.py.
    """
    restantes = [s for s in sistemas if s not in processados]
    if not restantes:
        return False
    return all(tentativas.get(s, 0) >= MAX_TENTATIVAS_LOGIN for s in restantes)


async def verificar_autenticacoes(sistemas: list[str]) -> dict[str, bool]:
    """
    Verifica quais sistemas têm sessão ativa consultando as abas abertas no Chrome
    via CDP HTTP — sem Playwright.

    Só responde pelos sistemas em que o endereço basta para decidir. Os de
    SEM_DETECCAO_DE_LOGIN saem sempre como False: para eles a URL não distingue
    logado de deslogado, e afirmar "logado" era exatamente o defeito que fazia o
    agente extrair antes da hora. Quem cuida desses é deve_tentar().

    ATENÇÃO antes de mexer aqui: já foi tentado ler o DOM das abas com Playwright
    para detectar o formulário de login (que é o que resolveria de verdade). Na
    máquina do Henrique a leitura falhou e, pior, o processo morreu com código -1
    no meio do primeiro CNJ — o Playwright do extrator não sobrevive a uma segunda
    instância aberta e fechada neste caminho. Este loop tem que ficar leve e sem
    Playwright. As peças da checagem boa continuam acima (_tem_campo_de_senha e o
    parâmetro tem_form_login de _avaliar_login), esperando uma forma de ler a
    página que não seja o Playwright — ver
    docs/deteccao-de-login-correcao-definitiva.md.
    """
    status: dict[str, bool] = {s: False for s in sistemas}
    for aba in _get_abas_chrome():
        url = aba.get("url", "")
        for sistema in sistemas:
            if sistema in SEM_DETECCAO_DE_LOGIN:
                continue
            # tem_form_login=False: sem leitura da página, só o endereço decide.
            if not status[sistema] and _avaliar_login(url, sistema, tem_form_login=False):
                status[sistema] = True
    return status


def abrir_aba_cdp(url: str) -> bool:
    """
    Abre uma aba no Chrome que já está na porta de debug. Devolve se conseguiu.

    O endpoint /json/new exige PUT desde o Chrome 111 — a chamada antiga era um
    GET (urlopen sem `data` manda GET) e voltava 405 em qualquer Chrome atual.
    O erro era engolido com um aviso, e o agente seguia sem aba nenhuma.
    """
    req = urllib.request.Request(f"{CDP_URL}/json/new?{url}", method="PUT")
    try:
        urllib.request.urlopen(req, timeout=5).close()
        return True
    except Exception:
        return False


async def abrir_abas_para_auth(sistemas_nao_autenticados: list[str]) -> None:
    """
    Abre uma aba no Chrome para cada sistema que precisa de login,
    usando o endpoint CDP HTTP — sem Playwright.
    Não abre se já existe uma aba para aquele sistema.
    """
    if not sistemas_nao_autenticados:
        return
    abas_existentes = _get_abas_chrome()
    for sistema in sistemas_nao_autenticados:
        url = SISTEMA_URLS.get(sistema)
        if not url:
            continue
        host = SISTEMA_HOST.get(sistema, "")
        if any(host in aba.get("url", "") for aba in abas_existentes):
            print(f"  Aba já aberta: {sistema}")
            continue
        if abrir_aba_cdp(url):
            print(f"  Aba aberta: {url}")
        else:
            print(f"  Aviso: não consegui abrir a aba de {sistema}")
            print(f"  Abra manualmente: {url}")


async def monitorar_logins_e_processar(
    sistemas: list[str],
    ao_logar: Callable[[str], Awaitable[bool]],
    timeout_s: int = 1500,
    intervalo_s: int = 3,
) -> set[str]:
    """
    Abre abas para os sistemas que precisam de login e fica monitorando.

    Sistema com detecção confiável (PJe): a extração dispara assim que o login
    aparece no endereço da aba, sem esperar os outros. Sistema sem detecção
    (SEM_DETECCAO_DE_LOGIN): não há sinal para esperar, então o agente dá
    ESPERA_LOGIN_S e tenta assim mesmo, até MAX_TENTATIVAS_LOGIN vezes — quem diz
    se havia sessão é o extrator, que lê a tela e acerta.

    `ao_logar` devolve False quando não havia sessão logo no primeiro processo
    (ninguém logou ainda). Só nesse caso o sistema volta para a fila de tentativas.
    Sistemas que não logarem a tempo são pulados e devolvidos à fila pelo runner.
    Retorna o conjunto de sistemas que foram processados.
    """
    loop = asyncio.get_running_loop()
    processados: set[str] = set()
    ja_avisados: set[str] = set()
    tentativas: dict[str, int] = {s: 0 for s in sistemas}
    ultima_tentativa: dict[str, float] = {s: loop.time() for s in sistemas}

    print("\nVerificando autenticação nos sistemas...")
    status = await verificar_autenticacoes(sistemas)
    ja_logados = [s for s, ok in status.items() if ok]
    nao_logados = [s for s, ok in status.items() if not ok]

    if ja_logados:
        print(f"  Sessão ativa: {', '.join(ja_logados)}")
    if nao_logados:
        print(f"  Necessita login: {', '.join(nao_logados)}")
        await abrir_abas_para_auth(nao_logados)

    cegos = [s for s in sistemas if s in SEM_DETECCAO_DE_LOGIN]
    com_deteccao = [s for s in sistemas if s not in SEM_DETECCAO_DE_LOGIN]

    print()
    if com_deteccao:
        print(f"  {', '.join(com_deteccao)}: a extração começa assim que o login for detectado.")
    if cegos:
        print(f"  {', '.join(cegos)}: não dá para conferir o login por aqui — a extração")
        print(f"  tenta a cada {ESPERA_LOGIN_S // 60} min, até {MAX_TENTATIVAS_LOGIN} vezes. "
              f"Faça login com calma.")
    print(f"  Tempo máximo de espera: {timeout_s // 60} min.\n")

    # Aqui havia uma pausa de 30s antes de extrair os sistemas já logados, para dar
    # tempo de concluir os logins pendentes. Não fazia sentido: 30 segundos não dão
    # para logar em sistema nenhum — o eProc e o RUPE ainda pedem um código que
    # chega por e-mail. E quem protege contra sessão que parece ativa mas expirou
    # agora é a retentativa, que é o extrator quem decide. Só atrasava o PJe.

    # zera o relógio antes do laço: o tempo gasto abrindo as abas não deve
    # consumir a espera de login de ninguém.
    inicio = loop.time()

    while len(processados) < len(sistemas):
        if loop.time() - inicio > timeout_s:
            restantes = [s for s in sistemas if s not in processados]
            print(f"\nTempo esgotado: {', '.join(restantes)} não respondeu — pulando.")
            break

        restantes = [s for s in sistemas if s not in processados]
        status = await verificar_autenticacoes(restantes)

        for sistema in restantes:
            detectado = status.get(sistema, False)
            if detectado and sistema not in ja_avisados:
                ja_avisados.add(sistema)
                print(f"  ✓ Login detectado: {sistema}")

            espera = loop.time() - ultima_tentativa[sistema]
            if not deve_tentar(sistema, detectado, espera, tentativas[sistema]):
                continue

            tentativas[sistema] += 1
            if sistema in SEM_DETECCAO_DE_LOGIN:
                print(f"  Tentando {sistema} — tentativa "
                      f"{tentativas[sistema]}/{MAX_TENTATIVAS_LOGIN}")

            if await ao_logar(sistema):
                processados.add(sistema)
                # zerar o contador após cada extração — o usuário tem tempo cheio
                # para logar no próximo sistema, independente de quanto demorou a extração anterior
                inicio = loop.time()
            else:
                print(f"  {sistema}: ainda sem login — nova tentativa em "
                      f"{ESPERA_LOGIN_S // 60} min.")
            # conta o intervalo a partir do FIM da tentativa: a extração em si pode
            # levar minutos, e contar do início encurtaria a espera do usuário.
            ultima_tentativa[sistema] = loop.time()

        if _esgotou_as_tentativas(sistemas, processados, tentativas):
            restantes = [s for s in sistemas if s not in processados]
            print(f"\n{', '.join(restantes)}: login não concluído em "
                  f"{MAX_TENTATIVAS_LOGIN} tentativas — pulando.")
            break

        if any(s not in processados for s in sistemas):
            await asyncio.sleep(intervalo_s)

    return processados


async def aguardar_login_automatico(
    sistemas: list[str],
    timeout_s: int = 600,
    intervalo_s: int = 3,
) -> bool:
    """
    Aguarda todos os sistemas logarem.

    NÃO SERVE para os sistemas de SEM_DETECCAO_DE_LOGIN: eles nunca aparecem como
    logados, então o `all(...)` abaixo jamais fecha e isto só devolve False no fim
    do timeout. Hoje ninguém chama por esse caminho — o fluxo automático é o
    monitorar_logins_e_processar, que trata esses sistemas por tentativa. Se um dia
    for preciso ressuscitar o modo abaixo, ele precisa da mesma lógica de tentativa.
    """
    loop = asyncio.get_event_loop()
    inicio = loop.time()
    ja_avisados: set[str] = set()

    print(f"\nAguardando login (extração começa sozinha). Sistemas: {', '.join(sistemas)}")
    print(f"Faça login em cada aba. Timeout: {timeout_s // 60} min.\n")

    while True:
        status = await verificar_autenticacoes(sistemas)

        for sistema, ok in status.items():
            if ok and sistema not in ja_avisados:
                ja_avisados.add(sistema)
                print(f"  ✓ Login detectado: {sistema}")

        if all(status.values()):
            print("\nTodos os sistemas logados. Iniciando extração automaticamente.\n")
            return True

        if loop.time() - inicio > timeout_s:
            faltando = [s for s, ok in status.items() if not ok]
            print(f"\nTimeout: login não concluído em {', '.join(faltando)}.")
            return False

        await asyncio.sleep(intervalo_s)


async def preparar_autenticacao(sistemas: list[str], modo_auto: bool = False) -> bool:
    """
    Verifica autenticação e aguarda o login do usuário.

    modo_auto=False → abre as abas faltantes e espera Enter (fluxo antigo).
    modo_auto=True  → não pede Enter; observa o Chrome e dispara sozinho
                      assim que todos os sistemas logarem.
    """
    print("\nVerificando autenticação nos sistemas...")
    status = await verificar_autenticacoes(sistemas)

    ja_logados = [s for s, ok in status.items() if ok]
    nao_logados = [s for s, ok in status.items() if not ok]

    if ja_logados:
        print(f"  Sessao ativa: {', '.join(ja_logados)}")

    if not nao_logados:
        print("Autenticacao confirmada. Iniciando extracoes.\n")
        return True

    print(f"  Necessita login: {', '.join(nao_logados)}")

    if modo_auto:
        return await aguardar_login_automatico(sistemas)

    print("\nAbrindo abas no Chrome...")
    await abrir_abas_para_auth(nao_logados)
    print("\nFaca login nos sistemas indicados.")
    print("Pressione Enter quando estiver pronto (ou Ctrl+C para cancelar)...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nCancelado.")
        return False

    print("Autenticacao confirmada. Iniciando extracoes.\n")
    return True
