"""
Script de diagnóstico — inspeciona a estrutura real da página do processo no PJE.
Rodar depois de já estar dentro do processo aberto.
"""
import asyncio
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:9222"


async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "pje.tjmg.jus.br" in pg.url:
                    page = pg
                    break

        if not page:
            print("ERRO: aba do PJE nao encontrada")
            await browser.close()
            return

        print(f"URL atual: {page.url}\n")

        # 1. Todos os frames da pagina
        print("=== FRAMES DISPONIVEIS ===")
        for i, frame in enumerate(page.frames):
            print(f"  [{i}] name={frame.name!r}  url={frame.url[:100]}")

        # 2. Todos os iframes no DOM
        print("\n=== IFRAMES NO DOM ===")
        iframes = await page.evaluate("""
            Array.from(document.querySelectorAll('iframe')).map(f => ({
                id: f.id,
                name: f.name,
                src: f.src,
                className: f.className
            }))
        """)
        for f in iframes:
            print(f"  id={f['id']!r}  name={f['name']!r}  src={f['src'][:80]!r}")

        # 3. Links de documentos na timeline
        print("\n=== LINKS DE DOCUMENTOS (.anexos a) ===")
        links = await page.evaluate("""
            Array.from(document.querySelectorAll('.anexos a')).slice(0, 5).map(a => ({
                href: a.href,
                text: a.innerText.trim().slice(0, 80),
                onclick: a.getAttribute('onclick') || ''
            }))
        """)
        for l in links:
            print(f"  text={l['text']!r}")
            print(f"    href={l['href'][:100]!r}")
            print(f"    onclick={l['onclick'][:100]!r}")

        # 4. Clicar no primeiro link e ver o que acontece
        print("\n=== CLICANDO NO PRIMEIRO LINK DE DOCUMENTO ===")
        primeiro = await page.query_selector('.anexos a')
        if primeiro:
            await page.evaluate("document.querySelector('.anexos a').click()")
            await page.wait_for_timeout(3000)

            print("Frames apos clique:")
            for i, frame in enumerate(page.frames):
                print(f"  [{i}] name={frame.name!r}  url={frame.url[:100]}")

            iframes2 = await page.evaluate("""
                Array.from(document.querySelectorAll('iframe')).map(f => ({
                    id: f.id, src: f.src
                }))
            """)
            print("Iframes no DOM apos clique:")
            for f in iframes2:
                print(f"  id={f['id']!r}  src={f['src'][:100]!r}")

            # verificar se o panel detalheDocumento ficou visivel
            visivel = await page.evaluate("""
                (() => {
                    const el = document.getElementById('detalheDocumento');
                    if (!el) return 'elemento nao encontrado';
                    const s = window.getComputedStyle(el);
                    return 'display=' + s.display + ' visibility=' + s.visibility;
                })()
            """)
            print(f"Panel #detalheDocumento: {visivel}")
        else:
            print("Nenhum link .anexos a encontrado na pagina atual")

        await browser.close()


asyncio.run(debug())
