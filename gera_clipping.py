import requests
from bs4 import BeautifulSoup
from google import genai
import time, os, smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

# 1. Configurações de Ambiente (Segurança)
api_key = os.environ.get("GEMINI_API_KEY")
email_user = os.environ.get("EMAIL_USER")
email_pass = os.environ.get("EMAIL_PASS")

client = genai.Client(api_key=api_key)

# --- FUNÇÕES DE SUPORTE PARA LISTAS EXTERNAS ---

def carregar_lista(nome_arquivo):
    """Lê arquivos .lista e retorna uma lista de strings limpas."""
    if os.path.exists(nome_arquivo):
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            # Filtra linhas vazias e remove espaços/quebras de linha
            return [linha.strip() for linha in f if linha.strip()]
    print(f"Aviso: Arquivo {nome_arquivo} não encontrado.")
    return []

def extrair_data(soup_artigo):
    """Tenta localizar a data de publicação no HTML da notícia."""
    data_tag = soup_artigo.find('meta', property='article:published_time')
    if data_tag:
        return datetime.fromisoformat(data_tag['content'].split('T')[0])
    time_tag = soup_artigo.find('time')
    if time_tag and time_tag.get('datetime'):
        return datetime.fromisoformat(time_tag['datetime'].split('T')[0])
    return None

def buscar_clipping_inteligente(termos):
    fontes = {"Teletime": "https://teletime.com.br/?s=", "TeleSíntese": "https://telesintese.com.br/?s="}
    noticias_filtradas = {}
    
    agora = datetime.now()
    # Lógica dinâmica: Segunda-feira (0) busca 72h, outros dias 24h
    horas_atras = 72 if agora.weekday() == 0 else 24
    limite_periodo = agora - timedelta(hours=horas_atras)
    
    print(f"Iniciando busca. Janela: {horas_atras} horas.")
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
                        res_art = requests.get(url_artigo, headers=headers, timeout=10)
                        soup_art = BeautifulSoup(res_art.text, 'html.parser')
                        data_pub = extrair_data(soup_art)

                        # Corrigido: usando limite_periodo (dinâmico) em vez de limite_24h
                        if data_pub and data_pub >= limite_periodo:
                            paragrafos = soup_art.find_all('p')
                            noticias_filtradas[url_artigo] = {
                                "titulo": link.get_text().strip(),
                                "fonte": nome_fonte,
                                "termo": termo,
                                "texto": " ".join([p.text for p in paragrafos[:4]])
                            }
                time.sleep(0.5)
            except: continue
    return noticias_filtradas

def processar_resumos_batch(dict_noticias):
    if not dict_noticias: return None
    prompt = "Resuma cada notícia abaixo em 3 pontos (Ação, Impacto, Valores). Separe com '---'.\n\n"
    for url, info in dict_noticias.items():
        prompt += f"TÍTULO: {info['titulo']}\nCONTEÚDO: {info['texto']}\n\n---\n\n"
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        resumos = response.text.split("---")
        for i, url in enumerate(dict_noticias.keys()):
            if i < len(resumos):
                dict_noticias[url]['resumo'] = resumos[i].strip().replace("\n", "<br>")
        return dict_noticias
    except: return dict_noticias

def enviar_email_html(lista_noticias, destinatarios):
    if not destinatarios:
        print("Erro: Nenhum destinatário encontrado na lista.")
        return

    msg = EmailMessage()
    data_hoje = time.strftime("%d/%m/%Y")
    msg['Subject'] = f'📌 Clipping Telecom & Infra - {data_hoje}'
    msg['From'] = email_user
    # Para enviar para vários, unimos a lista com vírgulas
    msg['To'] = ", ".join(destinatarios)

    html_corpo = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #0056b3; border-bottom: 2px solid #0056b3; padding-bottom: 10px;">
                Relatório Diário: Telecom e Infraestrutura
            </h2>
    """
    for url, item in lista_noticias.items():
        titulo = item.get('titulo', 'Sem título')
        fonte = item.get('fonte', 'Desconhecida')
        resumo = item.get('resumo', 'Sem resumo disponível.')
        
        html_corpo += f"""
        <div style="margin-bottom: 25px; padding: 15px; border-left: 5px solid #0056b3; background: #f9f9f9;">
            <strong>[{fonte}]</strong><br>
            <h3 style="margin: 5px 0;"><a href="{url}" style="color: #0056b3; text-decoration: none;">{titulo}</a></h3>
            <div style="background: #fff; padding: 10px; border: 1px solid #ddd; border-radius: 4px;">{resumo}</div>
        </div>
        """
    html_corpo += "</body></html>"
    msg.add_alternative(html_corpo, subtype='html')

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_user, email_pass)
            smtp.send_message(msg)
        print(f"E-mail enviado com sucesso para {len(destinatarios)} pessoas!")
    except Exception as e: print(f"Erro no envio: {e}")

# --- Execução Principal ---

# 1. Carrega as listas externas
emails_destino = carregar_lista("email_destino.lista")
termos_monitorados = carregar_lista("termos_chave.lista")

if not termos_monitorados:
    print("Erro: Nenhum termo para buscar. Verifique o arquivo termos_chave.lista.")
else:
    noticias = buscar_clipping_inteligente(termos_monitorados)

    if noticias:
        noticias_com_resumo = processar_resumos_batch(noticias)
        enviar_email_html(noticias_com_resumo, emails_destino)
    else:
        # Aviso de sistema ativo caso não encontre nada
        enviar_email_html({
            "https://status.com": {
                "titulo": "Monitoramento Ativo: Nenhuma novidade no período",
                "fonte": "Sistema",
                "resumo": "O robô realizou a varredura e não encontrou novos artigos para os termos monitorados."
            }
        }, emails_destino)
