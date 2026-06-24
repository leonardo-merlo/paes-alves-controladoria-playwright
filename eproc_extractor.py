"""
eproc_extractor.py — Extrai documentos de processos no eProc (1º grau).

Atende múltiplos tribunais que usam o mesmo eProc (INFRA): TJMG e TRF6. As páginas
são praticamente idênticas — muda só o host. O host/base é resolvido a partir do
número CNJ (via cnj_router): J.TT define o tribunal.

eProc é um sistema INFRA (mesma base dos TRFs). Diferenças importantes em relação
ao PJE que ditam a estratégia de extração:

  - Sessão única e agressiva: navegar para a URL de um documento (aba nova ou a
    mesma aba) derruba a sessão ("Sua sessão foi encerrada"). Os links de documento
    carregam um `hash` válido apenas no render atual da página.
  - Por isso NÃO navegamos para os documentos. Lemos o href fresco da tabela de
    eventos e baixamos o conteúdo via fetch() dentro da própria página autenticada
    (o fetch carrega o Referer correto e não troca de página).

Fluxo:
  1. Localiza a aba do eProc TJMG já logada (CDP).
  2. Pesquisa o processo pela busca rápida (#txtNumProcessoPesquisaRapida).
  3. Lê a tabela de eventos (#tblEventos) e os links de documento de cada evento.
  4. Para cada documento, faz fetch do conteúdo (HTML via DOMParser, PDF via PDF.js).

Mantém a mesma estrutura de retorno do pje_extractor.py.

Uso:
  python eproc_extractor.py <numero_cnj> [arquivo_saida.json]
"""

import asyncio
import json
import re
import sys
from datetime import datetime, timedelta
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, Playwright

CDP_URL = "http://localhost:9222"
TIMEOUT = 20_000
MAX_DOCS = 300

# eProc por tribunal (mesmo software INFRA, muda só o host)
SISTEMAS_EPROC = {
    "eproc_tjmg":    {"host": "eproc1g.tjmg.jus.br", "base": "https://eproc1g.tjmg.jus.br/eproc/"},
    "eproc_trf6":    {"host": "eproc1g.trf6.jus.br", "base": "https://eproc1g.trf6.jus.br/eproc/"},   # JFMG 1ª instância
    "eproc_trf6_2g": {"host": "eproc2g.trf6.jus.br", "base": "https://eproc2g.trf6.jus.br/eproc/"},   # TRF6 2ª instância
}
_DEFAULT_SISTEMA = "eproc_tjmg"

SELECTORS = {
    "campo_busca": "#txtNumProcessoPesquisaRapida",
    "tabela_eventos": "#tblEventos",
}


def _resolver_sistema(numero_cnj: str) -> tuple[str, str, str]:
    """Resolve (sistema, host, base) a partir do CNJ. Default: eProc TJMG."""
    try:
        from cnj_router import rotear
        sistema = rotear(numero_cnj).sistema
    except Exception:
        sistema = _DEFAULT_SISTEMA
    cfg = SISTEMAS_EPROC.get(sistema) or SISTEMAS_EPROC[_DEFAULT_SISTEMA]
    if sistema not in SISTEMAS_EPROC:
        sistema = _DEFAULT_SISTEMA
    return sistema, cfg["host"], cfg["base"]


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


async def encontrar_aba_eproc(browser: Browser, host: str) -> Page:
    # preferir a aba que tem a busca rápida (painel logado), evitando abas de documento
    candidatas = []
    for ctx in browser.contexts:
        for page in ctx.pages:
            if host in page.url:
                candidatas.append(page)

    for page in candidatas:
        try:
            tem_busca = await page.evaluate(
                f"!!document.querySelector('{SELECTORS['campo_busca']}')"
            )
            if tem_busca:
                return page
        except Exception:
            continue

    if candidatas:
        return candidatas[0]
    raise RuntimeError(f"Nenhuma aba do eProc ({host}) encontrada no Chrome conectado")


async def _esta_deslogado(page: Page) -> bool:
    try:
        return await page.evaluate(
            "/Entrar no Sistema|sess.o foi encerrada|externo_controlador/i"
            ".test((document.body?document.body.innerText:'') + location.href)"
        )
    except Exception:
        return False


async def verificar_sessao(page: Page) -> bool:
    if "externo_controlador" in page.url:
        return False
    if await _esta_deslogado(page):
        return False
    # painel_adv_listar e outras páginas do eProc não têm a busca rápida mas são sessões válidas
    # pesquisar_processo() navega ao painel principal se o campo não estiver presente
    return True


async def pesquisar_processo(page: Page, numero_cnj: str, base: str) -> None:
    campo = SELECTORS["campo_busca"]
    tem_campo = await page.evaluate(f"!!document.querySelector('{campo}')")
    if not tem_campo:
        # aceitar automaticamente o alert "Usuário logado como..." que o eProc exibe
        page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await page.goto(base + "controlador.php?acao=principal", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

    await page.fill(campo, numero_cnj)
    try:
        await page.press(campo, "Enter")
    except Exception:
        # fallback: servidor lento não respondeu ao keypress — submeter via JS não bloqueia
        await page.evaluate(f"document.querySelector('{campo}').form.submit()")

    # aguardar a tabela de eventos (até 45s — servidores lentos podem levar 30s+)
    try:
        await page.wait_for_selector(SELECTORS["tabela_eventos"], timeout=45_000, state="attached")
    except Exception:
        # verificar se acabou em `processo_selecionar` (lista de resultados) ou logout
        if "processo_selecionar" in page.url:
            pass  # ok — encontrou processo, selecionador vai aparecer
        elif await _esta_deslogado(page):
            raise RuntimeError("sessao_expirada")
        else:
            raise RuntimeError(
                f"Tabela de eventos não encontrada para {numero_cnj} — "
                "processo não localizado ou sessão expirada"
            )


def _parse_data(texto: str) -> datetime | None:
    m = re.search(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})", texto or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%d/%m/%Y %H:%M:%S")
    except Exception:
        return None


def _parse_corte(data_corte: str | None) -> datetime | None:
    if not data_corte:
        return None
    try:
        dt = datetime.fromisoformat(data_corte.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) - timedelta(days=1)
    except Exception:
        return None


async def ler_eventos(page: Page) -> list[dict]:
    """
    Lê TODOS os eventos da tabela, em ordem do DOM (mais recente → mais antigo).

    A descrição completa de cada evento é capturada porque ela frequentemente carrega
    informações que NÃO estão em nenhum documento: data/hora de audiência designada,
    a quem o prazo é dirigido ("RÉU - Banco X / Prazo: 15 dias"), e referências a
    outros eventos ("Refer. aos Eventos: 8, 9"). Eventos sem documento são mantidos —
    a resposta pode estar só na descrição (ex.: audiência designada).
    """
    return await page.evaluate(r"""
    () => {
        const rows = Array.from(document.querySelectorAll('#tblEventos tbody tr'));
        return rows.map(tr => {
            const tds = tr.querySelectorAll('td');
            const num  = tds[0] ? tds[0].innerText.trim() : '';
            const data = tds[1] ? tds[1].innerText.trim() : '';
            const desc = tds[2] ? tds[2].innerText.trim() : '';
            const userLines = (tds[3] ? tds[3].innerText.trim() : '')
                .split('\n').map(s => s.trim()).filter(Boolean);
            // eventos referenciados na descrição (ex.: "Refer. aos Eventos: 8, 9")
            const refMatch = desc.match(/Refer\.?\s*aos?\s*Eventos?:?\s*([\d,\s e]+)/i);
            const referencia = refMatch
                ? refMatch[1].split(/[,\se]+/).map(s => s.trim()).filter(Boolean)
                : [];
            const docs = Array.from(tr.querySelectorAll('a.infraLinkDocumento')).map(a => {
                const titleRaw = a.getAttribute('title') || '';
                return {
                    href:  a.getAttribute('href'),
                    nome:  a.getAttribute('data-nome'),
                    mime:  (a.getAttribute('data-mimetype') || '').toLowerCase(),
                    doc:   a.getAttribute('data-doc'),
                    rotulo: a.innerText.trim(),
                    titulo: titleRaw.split('\n')[0].trim(),
                };
            });
            return {
                num, data,
                descricao:     desc,
                parte:         tr.getAttribute('data-parte') || null,
                referencia,
                usuario_nome:  userLines[1] || userLines[0] || null,
                usuario_cargo: userLines[2] || null,
                docs,
            };
        });
    }
    """)


async def _garantir_pdfjs(page: Page) -> None:
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
    await page.wait_for_timeout(2500)


async def _extrair_pdf(page: Page, url: str) -> dict:
    """Baixa um PDF via fetch e extrai o texto com PDF.js. PDF escaneado → texto vazio."""
    await _garantir_pdfjs(page)
    texto = await page.evaluate(r"""
        async (url) => {
            if (!window.pdfjsLib) return 'ERRO_PDFJS: lib não carregada';
            try {
                const r = await fetch(url, { credentials: 'include' });
                const buf = await r.arrayBuffer();
                const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
                let t = '';
                for (let i = 1; i <= pdf.numPages; i++) {
                    const pg = await pdf.getPage(i);
                    const c = await pg.getTextContent();
                    t += c.items.map(s => s.str).join(' ') + '\n';
                }
                return t.trim();
            } catch (e) { return 'ERRO_PDFJS: ' + e.message; }
        }
    """, url)
    if texto and not texto.startswith("ERRO_PDFJS"):
        return {"texto": texto, "erro": None, "content_type": "application/pdf"}
    if texto.startswith("ERRO_PDFJS"):
        return {"texto": "", "erro": texto, "content_type": "application/pdf"}
    return {"texto": "", "erro": "[PDF escaneado — sem texto extraível]",
            "content_type": "application/pdf"}


async def baixar_texto_documento(page: Page, href: str, mime: str, base: str) -> dict:
    """
    Baixa o conteúdo de um documento via fetch dentro da página autenticada.
    Não navega — preserva a sessão (eProc derruba a sessão em navegação direta).

    O link 'acessar_documento' retorna um wrapper; a URL real do conteúdo
    ('acessar_documento_implementacao') é embutida via script — por isso a
    extraímos por regex no HTML cru, não por iframe. O conteúdo final pode ser
    HTML ou PDF.
    """
    url = href if href.startswith("http") else base + href

    info = await page.evaluate(r"""
        async (url) => {
            try {
                const r = await fetch(url, { credentials: 'include' });
                const ct = (r.headers.get('content-type') || '').toLowerCase();
                const buf = await r.arrayBuffer();
                const head = String.fromCharCode(...new Uint8Array(buf).slice(0, 5));
                if (ct.includes('pdf') || head === '%PDF') {
                    return { ehPdf: true };
                }
                const raw = new TextDecoder('iso-8859-1').decode(buf);
                if (r.url.includes('externo_controlador') ||
                    /sess.o foi encerrada|Entrar no Sistema/i.test(raw)) {
                    return { deslogado: true };
                }
                const m = raw.match(/controlador\.php\?acao=acessar_documento_implementacao[^"'\s)]+/);
                const implUrl = m ? m[0].replace(/&amp;/g, '&') : null;
                let wrapperText = '';
                try { wrapperText = new DOMParser().parseFromString(raw, 'text/html').body.innerText.trim(); }
                catch (e) {}
                return { ehPdf: false, implUrl, wrapperText };
            } catch (e) { return { erro: e.message }; }
        }
    """, url)

    if info.get("erro"):
        return {"texto": "", "erro": f"fetch_falhou: {info['erro']}", "content_type": None}
    if info.get("deslogado"):
        return {"texto": "", "erro": "sessao_expirada", "content_type": None}
    if info.get("ehPdf"):
        return await _extrair_pdf(page, url)

    impl = info.get("implUrl")
    if not impl:
        # sem URL de implementação — usar o texto do wrapper (caso raro)
        return {"texto": info.get("wrapperText", ""), "erro": None, "content_type": "text/html"}

    impl_url = impl if impl.startswith("http") else base + impl

    inner = await page.evaluate(r"""
        async (url) => {
            try {
                const r = await fetch(url, { credentials: 'include' });
                const ct = (r.headers.get('content-type') || '').toLowerCase();
                const buf = await r.arrayBuffer();
                if (ct.includes('pdf') ||
                    String.fromCharCode(...new Uint8Array(buf).slice(0, 5)) === '%PDF') {
                    return { ehPdf: true };
                }
                const raw = new TextDecoder('iso-8859-1').decode(buf);
                let txt = '';
                try { txt = new DOMParser().parseFromString(raw, 'text/html').body.innerText.trim(); }
                catch (e) {}
                return { ehPdf: false, texto: txt };
            } catch (e) { return { erro: e.message }; }
        }
    """, impl_url)

    if inner.get("erro"):
        return {"texto": "", "erro": f"fetch_impl_falhou: {inner['erro']}", "content_type": None}
    if inner.get("ehPdf"):
        return await _extrair_pdf(page, impl_url)
    return {"texto": inner.get("texto", ""), "erro": None, "content_type": "text/html"}


async def extrair_documentos(page: Page, eventos: list[dict], base: str, data_corte: str | None = None) -> list[dict]:
    documentos: list[dict] = []
    corte_dt = _parse_corte(data_corte)
    indice = 1

    for ev in eventos:
        ev_dt = _parse_data(ev.get("data", ""))
        # respeitar corte: pula eventos anteriores ao corte (já estavam no banco)
        if corte_dt and ev_dt and ev_dt < corte_dt:
            continue

        for d in ev["docs"]:
            res = await baixar_texto_documento(page, d["href"], d.get("mime", ""), base)
            if res.get("erro") == "sessao_expirada":
                raise RuntimeError("sessao_expirada")

            documentos.append({
                "indice":           indice,
                "numero_documento": d.get("doc"),
                "url_iframe":       d["href"] if d["href"].startswith("http") else base + d["href"],
                "texto":            res.get("texto", ""),
                "erro":             res.get("erro"),
                "titulo":           d.get("titulo") or d.get("rotulo"),
                "juntado_por":      ev.get("usuario_nome"),
                "cargo":            ev.get("usuario_cargo"),
                "data_documento":   ev.get("data"),
            })
            indice += 1
            if indice > MAX_DOCS:
                break
        if indice > MAX_DOCS:
            break

    # renumerar: 1 = mais antigo, N = mais recente (a tabela vem do mais novo p/ o mais antigo)
    total = len(documentos)
    for i, doc in enumerate(documentos):
        doc["indice"] = total - i

    return documentos


async def extrair_processo(numero_cnj: str, data_corte: str | None = None) -> dict:
    playwright: Optional[Playwright] = None
    browser: Optional[Browser] = None

    sistema, host, base = _resolver_sistema(numero_cnj)
    rotulo = "eProc TJMG" if sistema == "eproc_tjmg" else "eProc TRF6"

    try:
        playwright, browser = await conectar_cdp()
        page = await encontrar_aba_eproc(browser, host)
        page.set_default_timeout(TIMEOUT)

        if not await verificar_sessao(page):
            return {
                "erro":       "sessao_expirada",
                "numero_cnj": numero_cnj,
                "mensagem":   f"Henrique precisa autenticar novamente no {rotulo} (mesma aba, sem abrir nova)",
            }

        await pesquisar_processo(page, numero_cnj, base)
        eventos = await ler_eventos(page)
        documentos = await extrair_documentos(page, eventos, base, data_corte=data_corte)

        return {
            "sistema":            sistema,
            "numero_cnj":         numero_cnj,
            "total_documentos":   len(documentos),
            "metadados_timeline": eventos,
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
        if browser:
            await browser.close()  # CDP: close() apenas desconecta
        if playwright:
            await playwright.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python eproc_extractor.py <numero_cnj> [arquivo_saida.json]")
        print("Exemplo: python eproc_extractor.py 1001343-13.2026.8.13.0439")
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
