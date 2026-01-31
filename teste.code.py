import cloudscraper
from bs4 import BeautifulSoup
import time

def testar_acesso_exibidor(termo):
    url = f"https://www.exibidor.com.br/noticias/?s={termo}"
    
    # Criamos o scraper que simula um navegador de forma mais profunda
    # O parâmetro browser define qual navegador ele deve mimetizar
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )

    print(f"Tentando contornar bloqueio para: {url}...")
    
    try:
        # O cloudscraper substitui o requests.get
        response = scraper.get(url, timeout=20)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("Sucesso! O bloqueio foi contornado.\n")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Mantive seus seletores, mas adicionei uma busca por 'article' que é comum no Exibidor
            links = soup.select('section.lista-noticias .box-noticia a, .lista-noticias a, article a')
            
            if not links:
                print("Nenhuma notícia encontrada. O layout pode ter mudado.")
            else:
                # Usamos um set para evitar links duplicados (comum em scrapings de notícias)
                vistos = set()
                count = 1
                for link in links:
                    href = link.get('href')
                    titulo = link.get_text(strip=True)
                    
                    if href and titulo and href not in vistos:
                        full_url = href if href.startswith('http') else f"https://www.exibidor.com.br{href}"
                        print(f"{count}. {titulo}")
                        print(f"   Link: {full_url}\n")
                        vistos.add(href)
                        count += 1
                        if count > 5: break # Limite de 5 resultados
        else:
            print(f"Ainda recebendo erro {response.status_code}. O site reforçou a segurança.")
            
    except Exception as e:
        print(f"Erro inesperado: {e}")

if __name__ == "__main__":
    # Importante: instale antes com 'pip install cloudscraper'
    testar_acesso_exibidor("cinema")
