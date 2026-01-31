import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import time

def scrap_exibidor_v3(termo):
    options = uc.ChromeOptions()
    options.add_argument('--headless') # Roda sem abrir janela
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    print(f"Iniciando navegador indetectável para: {termo}...")
    
    try:
        driver = uc.Chrome(options=options)
        url = f"https://www.exibidor.com.br/noticias/?s={termo}"
        
        driver.get(url)

        # Espera estratégica para o desafio do site carregar
        time.sleep(5) 

        # Pegamos o HTML após a renderização do JavaScript
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        print(f"Título da página: {driver.title}")

        links = soup.select('section.lista-noticias .box-noticia a, .lista-noticias a')

        if not links:
            print("Ainda bloqueado ou seletores mudaram. Verifique o HTML.")
        else:
            for i, link in enumerate(links[:5], 1):
                titulo = link.get_text(strip=True)
                href = link['href']
                full_url = href if href.startswith('http') else f"https://www.exibidor.com.br{href}"
                print(f"{i}. {titulo}\n   Link: {full_url}\n")

        driver.quit()

    except Exception as e:
        print(f"Erro ao acessar: {e}")

if __name__ == "__main__":
    scrap_exibidor_v3("cinema")
