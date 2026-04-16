import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        print("Acessando http://localhost:8000/login ...")
        await page.goto("http://localhost:8000/login")
        
        # Fazendo login (assuming standard test credentials if any, otherwise I need to check routers/auth.py)
        # Let's check auth.py directly from the code since we don't know the password
        
        print("Login attempt failed or skipped, checking...")
        await browser.close()
        
if __name__ == "__main__":
    asyncio.run(run())
