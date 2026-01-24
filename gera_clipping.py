import requests
from bs4 import BeautifulSoup
from google import genai
import time, os, smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

# 1. Configurações de Ambiente
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY")) # cite: 1.1
email_user = os.environ.get("EMAIL_USER")
email_pass = os.environ.get("EMAIL_PASS")
email_destino = os.environ.get("EMAIL_DESTINO")

def extrair_data(soup_artigo):
    """Tenta localizar a data de publicação no HTML da notícia."""
    # Procura em tags comuns de tempo (meta tags ou classes de data)
    data_tag = soup_artigo.find('meta', property='article:published_time')
    if data_tag:
        return datetime.fromisoformat(data_tag['content'].split('T')[0])
    
    # Fallback para tags de tempo visíveis
    time_tag = soup_artigo.find('time')
    if time_tag and time_tag.get('datetime'):
        return datetime.fromisoformat(time_tag['datetime'].split('T')[0])
    return None

def buscar_clipping_24h(termos):
    fontes = {"Teletime": "https://teletime.com.br/?s=", "TeleSíntese": "https://telesintese.com.br/?s="}
    noticias_filtradas = {}
    limite_24h = datetime.now() - timedelta(hours=24)

    headers = {'User-Agent': 'Mozilla/5.0'}

    for nome_fonte, url_base in fontes.items():
        for termo in termos:
            termo_url = termo.replace(' ', '+').replace('"', '')
            try:
                res = requests.get(f"{url_base}{termo_url}", headers=headers, timeout=15)
                soup = BeautifulSoup(res.text, 'html.parser')
                links = soup.select('h2.entry-title a, h3.entry-title a')[:3]

                for link in links:
                    url_artigo = link['href']
                    if url_artigo not in noticias_filtradas:
                        # Acessa o artigo para validar a data
                        res_art = requests.get(url_artigo, headers=headers, timeout=10)
                        soup_art = BeautifulSoup(res_art.text, 'html.parser')
                        data_pub = extrair_data(soup_art)

                        # Filtro cronológico: só aceita se for das últimas 24h
                        if data_pub and data_pub >= limite_24h:
                            paragrafos = soup_art.find_all('p')
                            noticias_filtradas[url_artigo] = {
                                "titulo": link.get_text().strip(),
                                "fonte": nome_fonte,
                                "texto": " ".join([p.text for p in paragrafos[:4]])
                            }
                time.sleep(1)
            except: continue
    return noticias_filtradas

def processar_resumos_batch(dict_noticias):
    if not dict_noticias: return None
    
    prompt = "Você é um analista de telecom. Resuma cada notícia abaixo em 3 pontos curtos (Ação, Impacto, Valores). Separe os resumos com '---'.\n\n"
    for url, info in dict_noticias.items():
        prompt += f"TÍTULO: {info['titulo']}\nCONTEÚDO: {info['texto']}\n\n---\n\n"

    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt) # cite: 1.1, 2.1
        resumos = response.text.split("---")
        for i, url in enumerate(dict_noticias.keys()):
            if i < len(resumos):
                dict_noticias[url]['resumo'] = resumos[i].strip().replace("\n", "<br>")
    except: pass
    return dict_noticias

# --- Execução Principal ---
termos = ["FUST", "REDATA", "BRISANET", "FUNTTEL", "DATACENTER", "\"DATA CENTER\""]
noticias = buscar_clipping_24h(termos)

if noticias:
    noticias_com_resumo = processar_resumos_batch(noticias)
    # Aqui você chama sua função enviar_email_html(noticias_com_resumo)
    print(f"Sucesso! {len(noticias)} notícias recentes encontradas.")
else:
    print("Nenhuma novidade nas últimas 24 horas.")
