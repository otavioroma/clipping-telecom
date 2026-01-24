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
        # Converte quebras de linha da IA para <br> do HTML
        return response.text.replace("\n", "<br>")
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

def enviar_email_html(lista_noticias):
    msg = EmailMessage()
    data_hoje = time.strftime("%d/%m/%Y")
    msg['Subject'] = f'📌 Clipping Telecom & Infra - {data_hoje}'
    msg['From'] = email_user
    msg['To'] = email_destino

    # Construção do corpo HTML
    html_corpo = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <h2 style="color: #0056b3; border-bottom: 2px solid #0056b3; padding-bottom: 10px;">
                Relatório Diário: Telecom e Infraestrutura
            </h2>
            <p style="font-size: 0.9em; color: #666;">Data: {data_hoje}</p>
    """

    for item in lista_noticias:
        html_corpo += f"""
        <div style="margin-bottom: 25px; padding: 15px; border-left: 5px solid #0056b3; background-color: #f9f9f9;">
            <strong style="color: #d9534f;">[{item['Fonte']}]</strong> 
            <span style="font-weight: bold; color: #555;">(Termo: {item['Termo']})</span><br>
            <h3 style="margin: 10px 0;">
                <a href="{item['Link']}" style="color: #0056b3; text-decoration: none;">{item['Título']}</a>
            </h3>
            <p style="font-size: 0.95em; background: #fff; padding: 10px; border: 1px solid #ddd; border-radius: 4px;">
                {item['Resumo']}
            </p>
        </div>
        """

    html_corpo += """
            <hr>
            <p style="font-size: 0.8em; color: #888; text-align: center;">
                Enviado automaticamente via GitHub Actions & Google Gemini API.
            </p>
        </body>
    </html>
    """

    msg.add_alternative(html_corpo, subtype='html')

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_user, email_pass)
            smtp.send_message(msg)
        print("E-mail HTML enviado com sucesso!")
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")

# --- Execução Principal ---
termos_chave = ["FUST", "REDATA", "BRISANET", "FUNTTEL", "DATACENTER", "\"DATA CENTER\""]
meu_clipping = buscar_clipping(termos_chave)

if meu_clipping:
    enviar_email_html(meu_clipping)
else:
    print("Nenhuma notícia encontrada para os termos selecionados.")
