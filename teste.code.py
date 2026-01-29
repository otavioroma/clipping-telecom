import requests
from bs4 import BeautifulSoup

def testar_acesso_exibidor(termo):
    url = f"https://www.exibidor.com.br/noticias/?s={termo}"
    
    # Headers completos que mimetizam um navegador Chrome real
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.google.com/',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    print(f"Acessando: {url}...")
    
    try:
        # Usamos uma sessão para gerenciar cookies automaticamente
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=15)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("Sucesso! O site permitiu o acesso.\n")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Novo seletor baseado na estrutura atual do Exibidor
            links = soup.select('section.lista-noticias .box-noticia a, .lista-noticias a')
            
            if not links:
                print("Nenhuma notícia encontrada com os seletores atuais.")
            else:
                for i, link in enumerate(links[:5], 1):
                    titulo = link.get_text(strip=True)
                    href = link['href']
                    full_url = href if href.startswith('http') else f"https://www.exibidor.com.br{href}"
                    print(f"{i}. {titulo}")
                    print(f"   Link: {full_url}\n")
        else:
            print(f"Falha no acesso. Erro: {response.status_code}")
            
    except Exception as e:
        print(f"Erro inesperado: {e}")

if __name__ == "__main__":
    testar_acesso_exibidor("cinema")
