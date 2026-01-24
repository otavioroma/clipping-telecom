import requests
from bs4 import BeautifulSoup
from google import genai
import time
import os
import smtplib
from email.message import EmailMessage

# 1. Configuração de Variáveis de Ambiente
api_key = os.environ.get("GEMINI_API_KEY")
email_user = os.environ.get("EMAIL_USER")
email_pass = os.environ.get("EMAIL_PASS")
email_destino = os.environ.get("EMAIL_DESTINO")

client = genai.Client(api_key=api_key)

def buscar_clipping(termos):
    fontes = {
        "Teletime": "https://teletime.com.br/?s=",
        "TeleSíntese": "https://telesintese.com.br/?s="
    }
    noticias_unicas = {} # Chave será a URL para evitar duplicatas

    for nome_fonte, url_base in fontes.items():
        for termo in termos:
            termo_url = termo.replace(' ', '+').replace('"', '')
            url_busca = f"{url_base}{termo_url}"
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                res = requests.get(url_busca, headers=headers, timeout=15)
                soup = BeautifulSoup(res.text, 'html.parser')
                links = soup.select('h2.entry-title a, h3.entry-title a')[:2]

                for link in links:
                    url_artigo = link['href']
                    # Só adiciona se a URL ainda não foi coletada
                    if url_artigo not in noticias_unicas:
                        noticias_unicas[url_artigo] = {
                            "titulo": link.get_text().strip(),
                            "fonte": nome_fonte,
                            "termo": termo
                        }
            except Exception as e:
                print(f"Erro ao buscar '{termo}' em {nome_fonte}: {e}")
    return noticias_unicas

def processar_resumos_ia(dict_noticias):
    if not dict_noticias:
        return {}

    # Monta um único prompt gigante com todas as notícias para economizar chamadas
    prompt_batch = (
        "Você é um analista de infraestrutura de telecomunicações. "
        "Abaixo estão várias notícias. Para CADA UMA, gere um resumo de 3 tópicos (Ação, Impacto, Valores/Prazos). "
        "Mantenha a ordem e identifique-as pelo título.\n\n"
    )

    links_ordenados = list(dict_noticias.keys())
    for url in links_ordenados:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            paragrafos = soup.find_all('p')
            texto_base = " ".join([p.text for p in paragrafos[:4]]) # Reduzi para 4 parágrafos (mais economia)
            prompt_batch += f"TÍTULO: {dict_noticias[url]['titulo']}\nCONTEÚDO: {texto_base}\n\n---\n\n"
        except:
            continue

    try:
        # UMA ÚNICA CHAMADA À API PARA TUDO
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt_batch
        )
        # Dividimos a resposta da IA (usando o separador que pedimos ou confiando na estrutura)
        # Para facilitar o HTML, vamos tratar a resposta como um bloco único ou processar linhas
        resumos_brutos = response.text.split("---")
        
        # Atribuímos os resumos de volta ao dicionário
        for i, url in enumerate(links_ordenados):
            if i < len(resumos_brutos):
                dict_noticias[url]['resumo'] = resumos_brutos[i].strip().replace("\n", "<br>")
            else:
                dict_noticias[url]['resumo'] = "Resumo não disponível."
    except Exception as e:
        print(f"Erro na IA: {e}")
        for url in dict_noticias: dict_noticias[url]['resumo'] = "Erro ao gerar resumo."
    
    return dict_noticias

def enviar_email_html(lista_final):
    msg = EmailMessage()
    data_hoje = time.strftime("%d/%m/%Y")
    msg['Subject'] = f'📌 Clipping Telecom Otimizado - {data_hoje}'
    msg['From'] = email_user
    msg['To'] = email_destino

    html_corpo = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #0056b3; border-bottom: 2px solid #0056b3;">Relatório Diário Otimizado</h2>
            <p>Economia de API: Processadas {len(lista_final)} notícias únicas.</p>
    """

    for url, info in lista_final.items():
        html_corpo += f"""
        <div style="margin-bottom: 20px; padding: 10px; border-left: 5px solid #0056b3; background: #f4f4f4;">
            <strong>[{info['fonte']}]</strong> <br>
            <h3 style="margin: 5px 0;"><a href="{url}">{info['titulo']}</a></h3>
            <div style="background: #fff; padding: 8px; border: 1px solid #ddd;">
                {info.get('resumo', 'Sem resumo')}
            </div>
        </div>
        """

    html_corpo += "</body></html>"
    msg.add_alternative(html_corpo, subtype='html')

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_user, email_pass)
            smtp.send_message(msg)
        print("E-mail enviado!")
    except Exception as e: print(f"Erro e-mail: {e}")

# --- Execução ---
termos_chave = ["FUST", "REDATA", "BRISANET", "FUNTTEL", "DATACENTER", "\"DATA CENTER\""]
noticias = buscar_clipping(termos_chave)
if noticias:
    noticias_com_resumo = processar_resumos_ia(noticias)
    enviar_email_html(noticias_com_resumo)
else:
    print("Nada encontrado.")
