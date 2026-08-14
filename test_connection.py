import asyncio
from playwright.async_api import async_playwright

CDP_URL = "http://127.0.0.1:9222"


async def testar_conexao():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            print("CDP OK -- Chrome conectado")
            print(f"   Contextos abertos: {len(browser.contexts)}")
            for i, ctx in enumerate(browser.contexts):
                for j, page in enumerate(ctx.pages):
                    title = await page.title()
                    print(f"   [{i}.{j}] {title[:60]} -- {page.url[:80]}")
            await browser.close()
        except Exception as e:
            print(f"ERRO ao conectar: {e}")
            print("   Certifique-se de que o Chrome foi aberto com --remote-debugging-port=9222")


asyncio.run(testar_conexao())
