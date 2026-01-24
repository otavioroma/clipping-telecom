import requests
from bs4 import BeautifulSoup
from google import genai
import time
import os
import smtplib
from email.message import EmailMessage

# 1. Configuração de Variáveis de Ambiente (Injetadas pelo GitHub Actions)
api_key = os.environ.get("GEMINI_API_KEY")
email_user = os.environ.get("EMAIL_USER")
email_pass = os.environ.get("EMAIL_PASS")
email_destino = os.environ.get("EMAIL_DESTINO")

client = genai.Client(api_key=api_key)

def resumir_noticia(texto_completo):
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
            url_busca = f"{url_base}{termo.replace(' ', '+').replace('\"', '')}"
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                res = requests.get(url_busca, headers=headers, timeout=15)
                soup = BeautifulSoup(res.text, 'html.parser')
                links = soup.select('h2.entry-title a, h3.entry-title a')[:2]

                for link in links:
                    titulo = link.get_text().strip()
                    url_artigo = link['href']
                    
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
                    time.sleep(1)
            except Exception as e:
                print(f"Erro ao buscar '{termo}' em {nome_fonte}: {e}")
    return clipping_final

def enviar_email(corpo_clipping):
    msg = EmailMessage()
    msg['Subject'] = f'Clipping Telecom - {time.strftime("%d/%m/%Y")}'
    msg['From'] = email_user
    msg['To'] = email_destino
    msg.set_content(corpo_clipping)

    try:
        # Uso do servidor SMTP do Gmail com SSL
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_user, email_pass)
            smtp.send_message(msg)
        print("E-mail enviado com sucesso!")
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")

# --- Execução Principal ---
termos_chave = ["FUST", "REDATA", "BRISANET", "FUNTTEL", "DATACENTER", "\"DATA CENTER\""]
meu_clipping = buscar_clipping(termos_chave)

if meu_clipping:
    conteudo_email = "Relatório Diário de Notícias - Telecom e Infraestrutura\n\n"
    for item in meu_clipping:
        conteudo_email += f"[{item['Fonte']}] ({item['Termo']}) - {item['Título']}\n"
        conteudo_email += f"Link: {item['Link']}\n"
        conteudo_email += f"RESUMO:\n{item['Resumo']}\n"
        conteudo_email += "-" * 50 + "\n\n"
    
    # Imprime no log do GitHub e envia para o e-mail
    print(conteudo_email)
    enviar_email(conteudo_email)
else:
    print("Nenhuma notícia encontrada hoje.")
