import asyncio
from playwright.async_api import async_playwright
CDP_URL="http://localhost:9222"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.connect_over_cdp(CDP_URL)
        viva=False
        for c in b.contexts:
            for pg in c.pages:
                if "eproc1g.tjmg.jus.br" in pg.url and "externo_controlador" not in pg.url:
                    try:
                        if await pg.evaluate("!!document.querySelector('#txtNumProcessoPesquisaRapida') || !!document.querySelector('#tblEventos')"):
                            viva=True
                    except: pass
        print("SESSAO_EPROC_VIVA:", viva)
        await b.close()
asyncio.run(main())
