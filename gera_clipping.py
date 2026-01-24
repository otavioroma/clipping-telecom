import requests
from bs4 import BeautifulSoup
from google import genai
import time

# Configuração da API
client = genai.Client(api_key="SUA_CHAVE_AQUI")

def resumir_noticia(texto_completo):
    # Prompt focado em impacto técnico e de negócios
    prompt = (
        "Você é um analista de infraestrutura de telecomunicações. "
        "Resuma a notícia a seguir em 3 tópicos curtos, focando em: "
        "1. Ação principal | 2. Impacto para o setor | 3. Valores ou prazos envolvidos.\n\n"
        f"Conteúdo:\n{texto_completo}"
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Erro ao gerar resumo: {e}"

def buscar_clipping(termos):
    fontes = {
        "Teletime": "https://teletime.com.br/?s=",
        "TeleSíntese": "https://telesintese.com.br/?s="
    }
    
    clipping_final = []

    for nome_fonte, url_base in fontes.items():
        for termo in termos:
            # Formata o termo para a URL (ex: "data center" vira data+center)
            url_busca = f"{url_base}{termo.replace(' ', '+').replace('\"', '')}"
            
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                res = requests.get(url_busca, headers=headers, timeout=15)
                soup = BeautifulSoup(res.text, 'html.parser')

                # Seleciona os links das notícias (ajustado para os padrões dos portais)
                links = soup.select('h2.entry-title a, h3.entry-title a')[:2]

                for link in links:
                    titulo = link.get_text().strip()
                    url_artigo = link['href']
                    
                    # Extração do conteúdo para o resumo
                    res_artigo = requests.get(url_artigo, headers=headers)
                    soup_artigo = BeautifulSoup(res_artigo.text, 'html.parser')
                    paragrafos = soup_artigo.find_all('p')
                    texto_para_resumo = " ".join([p.text for p in paragrafos[:6]])

                    resumo = resumir_noticia(texto_para_resumo)
                    
                    clipping_final.append({
                        "Fonte": nome_fonte,
                        "Termo": termo,
                        "Título": titulo,
                        "Link": url_artigo,
                        "Resumo": resumo
                    })
                    
                    # Pausa curta para evitar bloqueio dos sites e respeitar cota da API
                    time.sleep(1)
            except Exception as e:
                print(f"Erro ao buscar '{termo}' em {nome_fonte}: {e}")

    return clipping_final

# Lista de termos atualizada
termos_chave = ["FUST", "REDATA", "BRISANET", "FUNTTEL", "DATACENTER", "\"DATA CENTER\""]

# Execução e exibição
meu_clipping = buscar_clipping(termos_chave)

for item in meu_clipping:
    print(f"[{item['Fonte']}] ({item['Termo']}) - {item['Título']}")
    print(f"Link: {item['Link']}")
    print(f"RESUMO:\n{item['Resumo']}")
    print("-" * 50)
