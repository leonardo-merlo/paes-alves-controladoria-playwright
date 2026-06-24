import asyncio
import json
import re
import sys
from datetime import datetime, timedelta
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, Playwright

CDP_URL = "http://localhost:9222"
PJE_URL = "https://pje.tjmg.jus.br/pje/Processo/ConsultaProcesso/listView.seam"
TIMEOUT = 20_000
MAX_DOCS = 300

SELECTORS = {
    "campo_sequencial":  '[id="fPP:numeroProcesso:numeroSequencial"]',
    "campo_digito":      '[id="fPP:numeroProcesso:numeroDigitoVerificador"]',
    "campo_ano":         '[id="fPP:numeroProcesso:Ano"]',
    "campo_orgao":       '[id="fPP:numeroProcesso:NumeroOrgaoJustica"]',
    "btn_pesquisar":     '[id="fPP:searchProcessos"]',
    "aba_documentos":    'a[href="#detalheDocumento"]',
    "iframe_documento":  '#frameBinario, #frameHtml',
    "btn_anterior":      '[id="detalheDocumento:documentoAnterior"]',
    "btn_proximo":       '[id="detalheDocumento:proximoDocumento"]',
    "items_timeline":    '.media.interno.tipo-D, .media.interno.tipo-M',
    "links_anexo":       '.anexos a',
    "span_id_doc":       '[id*="idDocumentoTimeLine"]',
}


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


async def encontrar_aba_pje(browser: Browser) -> Page:
    for ctx in browser.contexts:
        for page in ctx.pages:
            if "pje.tjmg.jus.br" in page.url:
                return page
    # fallback: primeira aba disponível
    for ctx in browser.contexts:
        if ctx.pages:
            return ctx.pages[0]
    raise RuntimeError("Nenhuma aba disponível no Chrome conectado")


async def verificar_sessao(page: Page) -> bool:
    await page.goto(PJE_URL)
    await page.wait_for_timeout(2000)

    url = page.url
    if "/login" in url:
        return False

    try:
        pwd_input = await page.query_selector('input[type="password"]')
        if pwd_input and await pwd_input.is_visible():
            return False
    except Exception:
        pass

    try:
        content = await page.content()
        if "sessão encerrada" in content.lower() or "token inválido" in content.lower():
            return False
    except Exception:
        pass

    return True


def _parse_cnj(numero_cnj: str) -> dict:
    # Formato: 5006107-76.2025.8.13.0384
    pattern = r'^(\d+)-(\d+)\.(\d{4})\.\d+\.\d+\.(\d+)$'
    m = re.match(pattern, numero_cnj.strip())
    if not m:
        raise ValueError(
            f"Número CNJ inválido: '{numero_cnj}'. "
            "Formato esperado: 5006107-76.2025.8.13.0384"
        )
    return {
        "sequencial": m.group(1),
        "digito":     m.group(2),
        "ano":        m.group(3),
        "orgao":      m.group(4),
    }


async def preencher_cnj(page: Page, numero_cnj: str) -> None:
    partes = _parse_cnj(numero_cnj)
    await page.fill(SELECTORS["campo_sequencial"], partes["sequencial"])
    await page.fill(SELECTORS["campo_digito"],     partes["digito"])
    await page.fill(SELECTORS["campo_ano"],        partes["ano"])
    await page.fill(SELECTORS["campo_orgao"],      partes["orgao"])


async def pesquisar_processo(page: Page, numero_cnj: str) -> None:
    await page.evaluate("window.confirm = () => true")
    await preencher_cnj(page, numero_cnj)
    await page.click(SELECTORS["btn_pesquisar"])

    # AJAX A4J — não sinaliza networkidle de forma confiável
    await page.wait_for_timeout(3000)

    # verificar reCAPTCHA
    recaptcha = await page.query_selector('div.g-recaptcha, iframe[src*="recaptcha"]')
    if recaptcha:
        raise RuntimeError(
            "reCAPTCHA detectado — Henrique precisa resolver manualmente no Chrome "
            "e depois rodar o script novamente"
        )

    await page.evaluate("window.scrollTo(0, 0)")


async def abrir_processo(page: Page, numero_cnj: str) -> None:
    # Injetar overrides antes do clique — popup blocker do Chrome bloqueia window.open
    await page.evaluate("""
        window.confirm = () => true;
        const _open = window.open;
        window.open = function(url, target, features) {
            if (url) { window.location.href = url; }
            return null;
        };
    """)
    await page.wait_for_timeout(1000)

    link = await page.query_selector(f'a[title="{numero_cnj}"]')
    if not link:
        raise RuntimeError(f"Processo {numero_cnj} não encontrado nos resultados")

    await link.click()
    await page.wait_for_timeout(4000)

    # Se não navegou (ainda em listView), tentar via script A4J embutido
    if "listView" in page.url:
        await page.evaluate("""
            window.confirm = () => true;
            window.open = function(url) { if (url) window.location.href = url; return null; };
            const s = Array.from(document.querySelectorAll('script'))
                .find(x => x.textContent.includes('listAutosDigitais') ||
                           x.textContent.includes('listProcessoCompleto'));
            if (s) eval(s.textContent);
        """)
        await page.wait_for_timeout(3000)


async def extrair_metadados_timeline(page: Page) -> list[dict]:
    metadados = []
    try:
        items = await page.query_selector_all(SELECTORS["items_timeline"])
        for item in items:
            # data
            data_el = await item.query_selector(".data-interna")
            data = (await data_el.inner_text()).strip() if data_el else ""

            # movimentos
            movs_els = await item.query_selector_all(".texto-movimento")
            movimentos = []
            for m in movs_els:
                txt = (await m.inner_text()).strip()
                if txt:
                    movimentos.append(txt)

            # documentos
            documentos = []
            links = await item.query_selector_all(SELECTORS["links_anexo"])
            for link in links:
                span = await link.query_selector(SELECTORS["span_id_doc"])
                if not span:
                    continue
                span_txt = (await span.inner_text()).strip()
                numero_match = re.search(r'(\d{10,})', span_txt)
                numero = numero_match.group(1) if numero_match else ""
                titulo = re.split(r'\s*-\s*', span_txt, maxsplit=1)[-1].strip()
                documentos.append({"numero": numero, "titulo": titulo})

            metadados.append({
                "data": data,
                "movimentos": movimentos,
                "documentos": documentos,
            })
    except Exception as e:
        metadados.append({"erro_metadados": str(e)})

    return metadados


async def extrair_texto_pdf(page: Page) -> str:
    # Etapa 1 — PDF com texto via PDF.js
    await page.evaluate("""
        if (!window._pdfjs_loaded) {
            const s = document.createElement('script');
            s.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
            s.onload = () => {
                pdfjsLib.GlobalWorkerOptions.workerSrc =
                    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
                window._pdfjs_loaded = true;
            };
            document.head.appendChild(s);
        }
    """)
    await page.wait_for_timeout(3000)

    texto = await page.evaluate("""
        async () => {
            const iframe = document.querySelector('#frameBinario, #frameHtml');
            const url = iframe?.src;
            if (!url || !window.pdfjsLib) return null;
            try {
                const r = await fetch(url, { credentials: 'include' });
                const buf = await r.arrayBuffer();
                const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
                let t = '';
                for (let i = 1; i <= pdf.numPages; i++) {
                    const pg = await pdf.getPage(i);
                    const c = await pg.getTextContent();
                    t += c.items.map(s => s.str).join(' ') + '\\n';
                }
                return t.trim() || null;
            } catch(e) {
                return 'ERRO_PDFJS: ' + e.message;
            }
        }
    """)

    if texto and not texto.startswith("ERRO_PDFJS"):
        return texto

    # Etapa 2 — PDF escaneado (fallback por screenshot)
    bbox = await page.evaluate("""
        const r = document.querySelector('#frameBinario, #frameHtml')?.getBoundingClientRect();
        r ? {x: r.x, y: r.y, width: r.width, height: r.height} : null
    """)
    if bbox:
        screenshot = await page.screenshot(clip=bbox)
        with open('/tmp/doc_screenshot.png', 'wb') as f:
            f.write(screenshot)

    return "[PDF_ESCANEADO — screenshot salvo em /tmp/doc_screenshot.png]"


async def extrair_texto_documento(page: Page) -> str:
    try:
        content_type = await page.evaluate("""
            document.querySelector('#frameBinario, #frameHtml')?.contentDocument?.contentType || ''
        """)

        if not content_type or content_type == "text/html":
            texto = await page.evaluate("""
                document.querySelector('#frameBinario, #frameHtml')?.contentDocument?.body?.innerText || ''
            """)
            return texto.strip()

        if content_type == "application/pdf":
            return await extrair_texto_pdf(page)

        # fallback via frame_locator (tentar cada seletor separado)
        for sel in ('#frameBinario', '#frameHtml'):
            try:
                return await page.frame_locator(sel).locator("body").inner_text(timeout=5000)
            except Exception:
                continue
        return ""

    except Exception as e:
        for sel in ('#frameBinario', '#frameHtml'):
            try:
                return await page.frame_locator(sel).locator("body").inner_text(timeout=5000)
            except Exception:
                continue
        return f"ERRO_EXTRACAO: {e}"


def _parse_corte(data_corte: str | None) -> datetime | None:
    if not data_corte:
        return None
    try:
        dt = datetime.fromisoformat(data_corte.replace("Z", "+00:00"))
        # remove timezone e subtrai 1 dia como margem de segurança
        return dt.replace(tzinfo=None) - timedelta(days=1)
    except Exception:
        return None


async def extrair_todos_documentos(page: Page, data_corte: str | None = None) -> list[dict]:
    documentos: list[dict] = []

    # Em telas grandes o #frameBinario já vem populado (N/N visível de cara)
    # Verificar se já tem src antes de tentar clicar em qualquer link
    src_inicial = await page.evaluate(
        "document.querySelector('#frameBinario, #frameHtml')?.src || ''"
    )

    if not src_inicial:
        # Tela pequena ou iframe ainda não carregado — clicar no primeiro documento
        primeiro_link = await page.query_selector(SELECTORS["links_anexo"])
        if not primeiro_link:
            return []
        try:
            await page.evaluate("""
                const link = document.querySelector('.anexos a');
                if (link) { link.scrollIntoView(); link.click(); }
            """)
            await page.wait_for_timeout(4000)
        except Exception as e:
            return [{"erro": f"Nao foi possivel abrir o primeiro documento: {e}"}]

    iframe = await page.query_selector(SELECTORS["iframe_documento"])
    if not iframe:
        return []

    indice = 1
    url_anterior = ""
    corte_dt = _parse_corte(data_corte)

    while True:
        # Polling: aguardar src mudar para um novo URL (diferente do anterior e não vazio)
        src_atual = ""
        for tentativa in range(20):
            await page.wait_for_timeout(1500)
            try:
                src_atual = await page.evaluate(
                    "document.querySelector('#frameBinario, #frameHtml')?.src || ''"
                )
            except Exception:
                src_atual = ""
            if not src_atual:
                continue
            if src_atual != url_anterior:
                break
            if tentativa >= 5:
                break

        if not src_atual or src_atual == url_anterior:
            break

        url_anterior = src_atual

        # URL real: /pje-legacy/documento/download/10692609597
        numero_match = re.search(r'/download/(\d+)', src_atual)
        numero_doc = numero_match.group(1) if numero_match else ""

        texto = ""
        erro = None
        try:
            texto = await extrair_texto_documento(page)
        except Exception as e:
            erro = str(e)

        # extrair metadados do painel: titulo, juntado_por, cargo, data_documento
        meta = await page.evaluate("""
            () => {
                const div = document.querySelector('.titulo-documento');
                if (!div) return {};
                const spanTitle = div.querySelector('span[title]');
                const titulo = spanTitle ? spanTitle.getAttribute('title').replace(/^\\d+\\s*-\\s*/, '').trim() : null;
                const texto = div.innerText || '';
                const m = texto.match(/Juntado por (.+?) - (.+?) em (\\d{2}\\/\\d{2}\\/\\d{4} \\d{2}:\\d{2}:\\d{2})/);
                return {
                    titulo:         titulo,
                    juntado_por:    m ? m[1].trim() : null,
                    cargo:          m ? m[2].trim() : null,
                    data_documento: m ? m[3].trim() : null,
                };
            }
        """)

        # parar se o documento for anterior ao corte (já estava no banco)
        if corte_dt and meta.get("data_documento"):
            try:
                doc_dt = datetime.strptime(meta["data_documento"], "%d/%m/%Y %H:%M:%S")
                if doc_dt < corte_dt:
                    break
            except Exception:
                pass  # se não parsear a data, continua extraindo

        documentos.append({
            "indice":           indice,
            "numero_documento": numero_doc,
            "url_iframe":       src_atual,
            "texto":            texto,
            "erro":             erro,
            "titulo":           meta.get("titulo"),
            "juntado_por":      meta.get("juntado_por"),
            "cargo":            meta.get("cargo"),
            "data_documento":   meta.get("data_documento"),
        })

        # verificar botão anterior
        btn_info = await page.evaluate("""
            (() => {
                const btn = document.querySelector('[id="detalheDocumento:documentoAnterior"]');
                if (!btn) return {found: false};
                return {found: true, disabled: btn.className.includes('disabled'), className: btn.className};
            })()
        """)

        if not btn_info.get("found") or btn_info.get("disabled"):
            break

        # descarregar PDF.js worker antes de clicar — evita interferência com A4J
        await page.evaluate("""
            if (window._pdfjs_loaded && window.pdfjsLib) {
                try { pdfjsLib.GlobalWorkerOptions.workerSrc = ''; } catch(e) {}
                window._pdfjs_loaded = false;
            }
        """)

        # usar click nativo do Playwright com force=True — dispara os eventos corretos para A4J
        try:
            await page.click('[id="detalheDocumento:documentoAnterior"]', force=True, timeout=5000)
        except Exception:
            # fallback para JS click
            await page.evaluate("""
                document.querySelector('[id="detalheDocumento:documentoAnterior"]')?.click()
            """)

        indice += 1
        if indice > MAX_DOCS:
            break

    # renumerar: 1 = mais antigo, N = mais recente
    total = len(documentos)
    for doc in documentos:
        doc["indice"] = total + 1 - doc["indice"]

    return documentos


async def extrair_processo(numero_cnj: str, data_corte: str | None = None) -> dict:
    playwright: Optional[Playwright] = None
    browser: Optional[Browser] = None

    try:
        playwright, browser = await conectar_cdp()
        page = await encontrar_aba_pje(browser)
        page.set_default_timeout(TIMEOUT)

        sessao_ok = await verificar_sessao(page)
        if not sessao_ok:
            return {
                "erro":       "sessao_expirada",
                "numero_cnj": numero_cnj,
                "mensagem":   "Henrique precisa autenticar novamente no PJE",
            }

        await pesquisar_processo(page, numero_cnj)
        await abrir_processo(page, numero_cnj)

        metadados = await extrair_metadados_timeline(page)
        documentos = await extrair_todos_documentos(page, data_corte=data_corte)

        return {
            "sistema":             "pje",
            "numero_cnj":          numero_cnj,
            "total_documentos":    len(documentos),
            "metadados_timeline":  metadados,
            "documentos":          documentos,
            "erros":               [d for d in documentos if d.get("erro")],
            "incremental":         bool(data_corte),
        }

    except Exception as e:
        return {"erro": str(e), "numero_cnj": numero_cnj}

    finally:
        if browser:
            await browser.close()  # em conexão CDP, close() apenas desconecta — não fecha o Chrome
        if playwright:
            await playwright.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python pje_extractor.py <numero_cnj> [arquivo_saida.json]")
        print("Exemplo: python pje_extractor.py 5006107-76.2025.8.13.0384")
        print("         python pje_extractor.py 5006107-76.2025.8.13.0384 resultado.json")
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
