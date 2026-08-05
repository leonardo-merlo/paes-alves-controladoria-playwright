"""
rupe_extractor.py — Extrai documentos de processos de 2ª instância do TJMG (RUPE).

A 2ª instância do TJMG roda no RUPE/PJe-Magistrado (pe.tjmg.jus.br), um sistema
JSF/RichFaces totalmente distinto do PJE (1º grau) e do eProc. Identificação pelo
CNJ: J=8, TT=13 e origem=0000 (o "0000" marca o tribunal/2ª instância).

Estratégia (descoberta por inspeção do DOM ao vivo) — evita os cliques AJAX frágeis:

  1. A Consulta de Processos tem link direto; navega-se direto na URL. Sem filtro de
     localização — ver o comentário em CONSULTA_PROCESSOS.
  2. O painel de Pesquisa Avançada nasce recolhido — 1 clique no toggle renderiza o
     input. O número CNJ formatado funciona no campo.
  3. A lupa do resultado carrega o idProcesso no próprio onclick — extraído por regex,
     sem clicar na lupa nem no botão "Visualizar Petições e Documentos".
  4. O visualizador de peças abre direto pela URL com idProcesso (sessão autenticada).
  5. Cada peça, ao ser clicada, só executa alterarArquivo(id, hash, ...), que aponta um
     iframe para uma URL de download direto do PDF. Em vez de clicar, montamos essa URL
     e baixamos os bytes pelo APIRequestContext do Playwright (compartilha a sessão e
     funciona em qualquer tamanho — o fetch in-page falha em arquivos grandes por
     Content-Disposition: attachment), extraindo o texto com PDF.js a partir dos bytes.

Mantém a mesma assinatura e o mesmo formato de retorno do pje_extractor/eproc_extractor.

Uso:
  python rupe_extractor.py <numero_cnj> [arquivo_saida.json]
"""

import asyncio
import base64
import json
import re
import sys
from datetime import datetime, timedelta
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, Playwright

from eproc_extractor import _garantir_pdfjs  # carrega PDF.js na página (reaproveitado)

CDP_URL = "http://localhost:9222"
TIMEOUT = 20_000
MAX_DOCS = 300
# Algumas peças do RUPE não baixam (o servidor trava ao montar o PDF assinado).
# Timeout curto no download faz pular rápido em vez de arrastar o lote inteiro.
DOWNLOAD_TIMEOUT_MS = 10_000   # peça boa baixa em <1,5s; peça que o servidor não entrega falha rápido
PARSE_TIMEOUT_S = 30           # teto p/ extração de texto via PDF.js (maior peça boa ~14s)

HOST = "pe.tjmg.jus.br"
BASE = "https://pe.tjmg.jus.br"
# Sem o "?acao=0&localizacaoAtual=862" que esta URL carregava até 05/08/2026: aquele
# filtro prende a busca à caixa "Meus Processos", e recurso que subiu da 1ª instância
# não está nela. Processos existentes e visíveis na mão voltavam como "nenhum
# resultado" — 5004160-55.2023.8.13.0384 (85 peças) e 5003155-90.2024.8.13.0439 são
# os casos que expuseram isso. Medido nos dois caminhos: com o filtro a lupa não
# aparece para eles e aparece para 0145032-91.2026.8.13.0000 (número nativo de 2ª
# instância); sem o filtro os três aparecem.
CONSULTA_PROCESSOS = f"{BASE}/rupe/portaljus/intranet/processo/processos.rupe"
VIEWER = (
    f"{BASE}/rupe/portaljus/intranet/processo/visualizadorPecasProcessuais/"
    "visualizadorPecasProcessuais.rupe?idProcesso={id}&visualizarPecasProcessoOrigem=false"
)
# URL de download direto do PDF da peça (montada a partir de idArquivo + hash)
DOWNLOAD = (
    f"{BASE}/rupe/portaljus/visualizarPecaProcessual?acao=download&viewFile=true"
    "&desenveloparArquivoAssinado=true&adicionarFolhaRosto=true"
    "&idArquivoDownload={id}&hashArquivo={hash}"
)

# IDs JSF (RichFaces) — contêm ':' e exigem getElementById, não querySelector
ID_TOGGLE = "formFiltrosfiltrosProcessos:toggleFiltrosfiltrosProcessos_header"
ID_INPUT = "formFiltrosfiltrosProcessos:processo"
ID_BOTAO = "formFiltrosfiltrosProcessos:pesquisar"

INDICADORES_DESLOGADO = ["/login", "efetuarLogin", "j_id_jsp", "Informe seu login"]


async def conectar_cdp() -> tuple[Playwright, Browser]:
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.connect_over_cdp(CDP_URL)
        return playwright, browser
    except Exception as e:
        raise RuntimeError(
            f"Não foi possível conectar ao Chrome via CDP ({CDP_URL}): {e}\n"
            "Abra o Chrome com: chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\\chrome-debug"
        )


async def encontrar_aba_rupe(browser: Browser) -> Page:
    """Aba principal do RUPE (logada), ignorando abas do visualizador de peças."""
    candidatas = []
    for ctx in browser.contexts:
        for page in ctx.pages:
            if HOST in page.url and "visualizadorPecas" not in page.url:
                candidatas.append(page)
    if candidatas:
        return candidatas[0]
    raise RuntimeError(f"Nenhuma aba do RUPE ({HOST}) encontrada no Chrome conectado")


async def verificar_sessao(page: Page) -> bool:
    """Sessão viva = menu 'Meus Processos' acessível, sem redirecionamento p/ login."""
    try:
        await page.goto(CONSULTA_PROCESSOS, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
    except Exception:
        return False
    if any(ind in page.url for ind in INDICADORES_DESLOGADO):
        return False
    try:
        return await page.evaluate(
            f"!!document.getElementById({json.dumps(ID_TOGGLE)})"
        )
    except Exception:
        return False


async def _expandir_pesquisa(page: Page) -> None:
    tem_input = await page.evaluate(f"!!document.getElementById({json.dumps(ID_INPUT)})")
    if tem_input:
        return
    await page.evaluate(f"document.getElementById({json.dumps(ID_TOGGLE)}).click()")
    for _ in range(15):
        await page.wait_for_timeout(800)
        if await page.evaluate(f"!!document.getElementById({json.dumps(ID_INPUT)})"):
            return
    raise RuntimeError("Painel de Pesquisa Avançada não abriu (input não renderizou)")


async def pesquisar_processo(page: Page, numero_cnj: str) -> str:
    """Pesquisa o processo e retorna o idProcesso extraído do onclick da lupa."""
    await _expandir_pesquisa(page)

    await page.evaluate(
        f"""() => {{
            const inp = document.getElementById({json.dumps(ID_INPUT)});
            inp.value = {json.dumps(numero_cnj)};
        }}"""
    )
    await page.evaluate(f"document.getElementById({json.dumps(ID_BOTAO)}).click()")

    # aguardar a tabela de resultados (lupa) ou mensagem de "nenhum registro"
    onclick = None
    for _ in range(25):
        await page.wait_for_timeout(800)
        try:
            onclick = await page.evaluate(
                """() => {
                    const img = document.querySelector('img[src*="visualizar"]');
                    return img ? img.getAttribute('onclick') : null;
                }"""
            )
        except Exception:
            continue  # contexto destruído por navegação em curso — aguardar próxima iteração
        if onclick:
            break

    if not onclick:
        raise RuntimeError(
            f"Processo {numero_cnj} não localizado no RUPE "
            "(nenhum resultado na pesquisa)"
        )

    m = re.search(r"dataTabletabelaProcessos:(\d+):", onclick)
    if not m:
        raise RuntimeError(
            f"idProcesso não encontrado no resultado de {numero_cnj}"
        )
    return m.group(1)


async def ler_pecas(viewer: Page) -> list[dict]:
    """
    Lê TODAS as peças da lista lateral, em ordem do DOM.

    No DOM, índice 0 = peça nº 1 (mais antiga) e índice N = peça mais recente.
    Cada link carrega alterarArquivo(idArquivo, hash, nome, tipo, situacao); a linha
    (<tr>) traz número, data de inclusão e quem assinou. O primeiro <a> da tabela é
    um controle (j_id47) e é descartado pelo seletor (id termina em j_id85).
    """
    return await viewer.evaluate(r"""
    () => {
        const links = Array.from(
            document.querySelectorAll('a[id*="tabelaPecasProcessuais"][id$="j_id85"]')
        );
        return links.map((a, i) => {
            const oc = a.getAttribute('onclick') || '';
            const m = oc.match(
                /alterarArquivo\(\s*'([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'/
            );
            const tr = a.closest('tr');
            const tds = tr ? Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()) : [];
            const after = (label) => {
                const idx = tds.findIndex(t => t === label);
                return (idx >= 0 && tds[idx + 1] !== undefined) ? tds[idx + 1] : '';
            };
            const numero = (tds.find(t => /^\d+$/.test(t)) || String(i + 1));
            const assinado = after('Assinado por:').split('\n')[0].trim();
            return {
                dom_index:     i,
                numero:        numero,
                id_arquivo:    m ? m[1] : null,
                hash:          m ? m[2] : null,
                nome_arquivo:  m ? m[3] : after('Nome:'),
                tipo:          m ? m[4] : a.innerText.trim(),
                situacao:      m ? m[5] : after('Situação:'),
                data_inclusao: after('Inclusão:'),
                assinado_por:  assinado || null,
            };
        });
    }
    """)


def _parse_data(texto: str) -> datetime | None:
    m = re.search(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}(?::\d{2})?)", texto or "")
    if not m:
        return None
    bruto = m.group(1)
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(bruto, fmt)
        except ValueError:
            continue
    return None


def _parse_corte(data_corte: str | None) -> datetime | None:
    if not data_corte:
        return None
    try:
        dt = datetime.fromisoformat(data_corte.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) - timedelta(days=1)
    except Exception:
        return None


async def _baixar_e_extrair_pdf(page: Page, url: str) -> dict:
    """
    Baixa a peça pelo APIRequestContext (compartilha a sessão e funciona em qualquer
    tamanho — o fetch in-page falha em arquivos grandes por Content-Disposition) e
    extrai o texto com PDF.js a partir dos bytes. PDF.js deve já estar carregado na
    página. PDF escaneado (sem camada de texto) → texto vazio com marca explícita.
    """
    try:
        resp = await page.context.request.get(url, timeout=DOWNLOAD_TIMEOUT_MS)
    except Exception as e:
        return {"texto": "", "erro": f"download_falhou: {str(e).splitlines()[0]}", "content_type": None}
    if resp.status != 200:
        return {"texto": "", "erro": f"http_{resp.status}", "content_type": None}

    body = await resp.body()
    ct = (resp.headers.get("content-type") or "").lower()

    if not (body[:4] == b"%PDF" or "pdf" in ct):
        # conteúdo textual (HTML/txt) — decodifica e remove marcação
        bruto = body.decode("utf-8", errors="replace")
        texto = await page.evaluate(
            "(html) => { try { return new DOMParser()"
            ".parseFromString(html,'text/html').body.innerText.trim(); }"
            " catch(e){ return ''; } }",
            bruto,
        )
        return {"texto": texto, "erro": None, "content_type": ct or "text/html"}

    b64 = base64.b64encode(body).decode("ascii")
    try:
        texto = await asyncio.wait_for(page.evaluate(r"""
            async (b64) => {
                if (!window.pdfjsLib) return 'ERRO_PDFJS: lib não carregada';
                try {
                    const bin = atob(b64);
                    const arr = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
                    const pdf = await pdfjsLib.getDocument({ data: arr }).promise;
                    let t = '';
                    for (let i = 1; i <= pdf.numPages; i++) {
                        const pg = await pdf.getPage(i);
                        const c = await pg.getTextContent();
                        t += c.items.map(s => s.str).join(' ') + '\n';
                    }
                    return t.trim();
                } catch (e) { return 'ERRO_PDFJS: ' + e.message; }
            }
        """, b64), timeout=PARSE_TIMEOUT_S)
    except asyncio.TimeoutError:
        return {"texto": "", "erro": f"[PDF.js excedeu {PARSE_TIMEOUT_S}s — peça pulada]",
                "content_type": "application/pdf"}

    if texto.startswith("ERRO_PDFJS"):
        return {"texto": "", "erro": texto, "content_type": "application/pdf"}
    if not texto:
        return {"texto": "", "erro": "[PDF escaneado — sem texto extraível]",
                "content_type": "application/pdf"}
    return {"texto": texto, "erro": None, "content_type": "application/pdf"}


async def extrair_documentos(
    viewer: Page, pecas: list[dict], data_corte: str | None = None
) -> list[dict]:
    """Baixa o texto das peças da mais recente para a mais antiga, respeitando o corte."""
    documentos: list[dict] = []
    corte_dt = _parse_corte(data_corte)
    await _garantir_pdfjs(viewer)  # carrega PDF.js uma vez antes do loop

    # mais recente → mais antiga (índice DOM alto → baixo)
    for peca in sorted(pecas, key=lambda p: p["dom_index"], reverse=True):
        if not peca.get("id_arquivo") or not peca.get("hash"):
            continue

        peca_dt = _parse_data(peca.get("data_inclusao", ""))
        if corte_dt and peca_dt and peca_dt < corte_dt:
            continue

        url = DOWNLOAD.format(id=peca["id_arquivo"], hash=peca["hash"])
        res = await _baixar_e_extrair_pdf(viewer, url)

        documentos.append({
            "indice":           0,  # renumerado abaixo
            "numero_documento": peca.get("numero"),
            "url_iframe":       url,
            "texto":            res.get("texto", ""),
            "erro":             res.get("erro"),
            "titulo":           peca.get("tipo") or peca.get("nome_arquivo"),
            "juntado_por":      peca.get("assinado_por"),
            "cargo":            None,
            "data_documento":   peca.get("data_inclusao"),
        })
        if len(documentos) >= MAX_DOCS:
            break

    # renumerar: 1 = mais antigo, N = mais recente (lista veio do mais novo p/ o mais antigo)
    total = len(documentos)
    for i, doc in enumerate(documentos):
        doc["indice"] = total - i

    return documentos


async def extrair_processo(numero_cnj: str, data_corte: str | None = None, sistema_hint: str | None = None) -> dict:
    playwright: Optional[Playwright] = None
    browser: Optional[Browser] = None
    viewer: Optional[Page] = None
    rotulo = "RUPE TJMG (2ª instância)"

    try:
        playwright, browser = await conectar_cdp()
        page = await encontrar_aba_rupe(browser)
        page.set_default_timeout(TIMEOUT)

        if not await verificar_sessao(page):
            return {
                "erro":       "sessao_expirada",
                "numero_cnj": numero_cnj,
                "mensagem":   f"Henrique precisa autenticar novamente no {rotulo} (mesma aba)",
            }

        id_processo = await pesquisar_processo(page, numero_cnj)

        viewer = await page.context.new_page()
        viewer.set_default_timeout(TIMEOUT)
        await viewer.goto(VIEWER.format(id=id_processo), wait_until="domcontentloaded")
        await viewer.wait_for_timeout(2500)

        pecas = await ler_pecas(viewer)
        if not pecas:
            return {
                "erro":       "nenhuma_peca",
                "numero_cnj": numero_cnj,
                "mensagem":   f"Visualizador abriu mas nenhuma peça foi listada (idProcesso={id_processo})",
            }

        documentos = await extrair_documentos(viewer, pecas, data_corte=data_corte)

        return {
            "sistema":            "pje_tjmg_2inst",
            "numero_cnj":         numero_cnj,
            "id_processo":        id_processo,
            "total_documentos":   len(documentos),
            "metadados_timeline": pecas,
            "documentos":         documentos,
            "erros":              [d for d in documentos if d.get("erro")],
            "incremental":        bool(data_corte),
        }

    except RuntimeError as e:
        if "sessao_expirada" in str(e):
            return {"erro": "sessao_expirada", "numero_cnj": numero_cnj,
                    "mensagem": f"Henrique precisa autenticar novamente no {rotulo}"}
        return {"erro": str(e), "numero_cnj": numero_cnj}
    except Exception as e:
        return {"erro": str(e), "numero_cnj": numero_cnj}
    finally:
        if viewer:
            try:
                await viewer.close()  # fecha apenas a aba do visualizador que abrimos
            except Exception:
                pass
        if browser:
            await browser.close()  # CDP: close() apenas desconecta
        if playwright:
            await playwright.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python rupe_extractor.py <numero_cnj> [arquivo_saida.json]")
        print("Exemplo: python rupe_extractor.py 0372800-08.2026.8.13.0000")
        sys.exit(1)

    numero_cnj = sys.argv[1]
    arquivo_saida = sys.argv[2] if len(sys.argv) > 2 else None

    resultado = asyncio.run(extrair_processo(numero_cnj))
    saida = json.dumps(resultado, ensure_ascii=False, indent=2)

    if arquivo_saida:
        with open(arquivo_saida, "w", encoding="utf-8") as f:
            f.write(saida)
        print(f"Salvo em {arquivo_saida}")
    else:
        print(saida)
