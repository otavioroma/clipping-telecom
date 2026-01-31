from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def scrap_exibidor_playwright(termo):
    url = f"https://www.exibidor.com.br/noticias/?s={termo}"
    
    with sync_playwright() as p:
        # Lança o navegador. O Playwright gerencia a versão correta!
        browser = p.chromium.launch(headless=True)
        
        # Criamos um contexto com um User-Agent real
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        print(f"Acessando: {url}...")

        try:
            # O Playwright espera a página carregar de forma inteligente
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Pegamos o HTML final (pós-JavaScript)
            soup = BeautifulSoup(page.content(), 'html.parser')
            
            print(f"Sucesso! Página carregada: {page.title()}")

            # Seletores originais do seu script
            links = soup.select('section.lista-noticias .box-noticia a, .lista-noticias a')

            if not links:
                print("Nenhum resultado encontrado. O site pode ter mudado o layout ou bloqueado o IP.")
            else:
                for i, link in enumerate(links[:5], 1):
                    titulo = link.get_text(strip=True)
                    href = link.get('href', '')
                    full_url = href if href.startswith('http') else f"https://www.exibidor.com.br{href}"
                    if titulo:
                        print(f"{i}. {titulo}\n   Link: {full_url}\n")

        except Exception as e:
            print(f"Erro na execução: {e}")
        
        finally:
            browser.close()

if __name__ == "__main__":
    scrap_exibidor_playwright("cinema")
