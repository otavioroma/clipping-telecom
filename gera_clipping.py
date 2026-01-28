import requests
from bs4 import BeautifulSoup
from google import genai
import time, os, smtplib, logging
from datetime import datetime, timedelta
from email.message import EmailMessage

# Configura o log para salvar em 'clipping.log'
logging.basicConfig(
    filename='clipping.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# 1. Configurações de Ambiente
api_key = os.environ.get("GEMINI_API_KEY")
email_user = os.environ.get("EMAIL_USER")
email_pass = os.environ.get("EMAIL_PASS")

client = genai.Client(api_key=api_key)

# --- FUNÇÕES DE SUPORTE ---

def carregar_lista(nome_arquivo):
    if os.path.exists(nome_arquivo):
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            return [linha.strip() for linha in f if linha.strip()]
    return []

def extrair_data(soup_artigo):
    data_tag = soup_artigo.find('meta', property='article:published_time')
    if data_tag:
        return datetime.fromisoformat(data_tag['content'].split('T')[0])
    time_tag = soup_artigo.find('time')
    if time_tag and time_tag.get('datetime'):
        return datetime.fromisoformat(time_tag['datetime'].split('T')[0])
    return None

def formatar_resumo_telecom(texto_retornado_ia):
    """Formata o texto da IA em blocos <div> para garantir que o Outlook respeite as quebras de linha."""
    if not texto_retornado_ia: return ""
    linhas = texto_retornado_ia.strip().split('\n')
    linhas_finalizadas = []
    
    for linha in linhas:
        linha = linha.strip()
        if not linha or any(x in linha.upper() for x in ["TÍTULO:", "RESUMO:"]):
            continue

        substituicoes = {
            "Ação:": "<strong>Ação:</strong>",
            "Impacto:": "<strong>Impacto:</strong>",
            "Valores:": "<strong>Números:</strong>",
            "Números:": "<strong>Números:</strong>"
        }
        
        encontrou_topico = False
        for original, negrito in substituicoes.items():
            if original in linha:
                linha = linha.replace(original, negrito)
                encontrou_topico = True
                break
        
        if encontrou_topico:
            linhas_finalizadas.append(f'<div style="margin-bottom: 8px; display: block;">{linha}</div>')

    return "".join(linhas_finalizadas)

# --- FUNÇÃO DE BUSCA SEGMENTADA ---

def buscar_clipping_inteligente(termos_telecom, termos_cinema):
    fontes_telecom = {
        "TeleTime": "https://teletime.com.br/?s=", 
        "TeleSíntese": "https://telesintese.com.br/?s=",
        "MobileTime": "https://www.mobiletime.com.br/?s="
    }
    fontes_cinema = {
        "TelaViva": "https://telaviva.com.br/?s=",
        "PortalExibidor": "https://www.exibidor.com.br/?s=",
        "FilmeB": "https://www.filmeb.com.br/?s="
    }

    noticias_filtradas = {}
    agora = datetime.now()
    horas_atras = 72 if agora.weekday() == 0 else 24
    limite_periodo = (agora - timedelta(hours=horas_atras)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    def executar_varredura(lista_fontes, lista_termos, categoria):
        for nome_fonte, url_base in lista_fontes.items():
            for termo in lista_termos:
                termo_url = termo.replace(' ', '+').replace('"', '')
                try:
                    res = requests.get(f"{url_base}{termo_url}", headers=headers, timeout=15)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    
                    if "filmeb" in url_base:
                        links = soup.select('div.noticias-lista h3 a, .post-title a')[:3]
                    elif "exibidor" in url_base:
                        links = soup.select('.noticia-item h2 a, .noticias-lista a')[:3]
                    elif "telaviva" in url_base:
                        links = soup.select('#main h2.entry-title a, #primary h2.entry-title a')[:5]
                    else:
                        links = soup.select('h2.entry-title a, h3.entry-title a')[:3]

                    for link in links:
                        url_artigo = link['href']
                        blacklist = ['quem-somos', 'anuncie', 'contato', 'expediente', 'politica-de-privacidade']
                        if any(sujo in url_artigo.lower() for sujo in blacklist): continue

                        if url_artigo not in noticias_filtradas:
                            res_art = requests.get(url_artigo, headers=headers, timeout=10)
                            soup_art = BeautifulSoup(res_art.text, 'html.parser')
                            data_pub = extrair_data(soup_art)

                            if data_pub and data_pub >= limite_periodo:
                                paragrafos = soup_art.find_all('p')
                                texto_extraido = " ".join([p.text for p in paragrafos[:5]])
                                if len(texto_extraido) > 100:
                                    noticias_filtradas[url_artigo] = {
                                        "titulo": link.get_text().strip(),
                                        "fonte": nome_fonte,
                                        "categoria": categoria,
                                        "texto": texto_extraido
                                    }
                    time.sleep(0.5)
                except Exception as e:
                    logging.error(f"Erro na fonte {nome_fonte}: {e}")

    executar_varredura(fontes_telecom, termos_telecom, "TELECOM")
    executar_varredura(fontes_cinema, termos_cinema, "CINEMA")
    return noticias_filtradas

# --- PROCESSAMENTO IA ---

def processar_resumos_batch(dict_noticias):
    if not dict_noticias: return {}
    
    prompt = (
        "Você é um Analista de Mercado Sênior em Telecomunicações e Audiovisual.\n"
        "Sua tarefa é criar resumos técnicos baseados no conteúdo fornecido.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Para cada notícia, gere um resumo com exatamente 3 campos: Ação:, Impacto: e Valores:.\n"
        "2. IMPORTANTE: Use o separador '---' (três hífens) estritamente entre os resumos de notícias diferentes.\n"
        "3. Se a notícia for irrelevante ao setor de infraestrutura ou cinema, escreva apenas 'DESCARTAR' para aquela notícia.\n"
        "4. Não use negritos ou markdown.\n\n"
    )
    
    links_ordenados = list(dict_noticias.keys())
    for url in links_ordenados:
        prompt += f"URL: {url}\nTÍTULO: {dict_noticias[url]['titulo']}\nCONTEÚDO: {dict_noticias[url]['texto']}\n\n---\n\n"

    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        texto_ia = response.text
        logging.info(f"RESPOSTA BRUTA DA IA RECEBIDA. Tamanho: {len(texto_ia)}")
        
        # Split e limpeza de resumos vazios
        resumos = [r.strip() for r in texto_ia.split("---") if len(r.strip()) > 5]
        
        finalizadas = {}
        for i, resumo_bruto in enumerate(resumos):
            if i < len(links_ordenados):
                url = links_ordenados[i]
                if "DESCARTAR" not in resumo_bruto.upper():
                    dict_noticias[url]['resumo'] = formatar_resumo_telecom(resumo_bruto)
                    finalizadas[url] = dict_noticias[url]
                else:
                    logging.warning(f"IA descartou: {url}")
        
        return finalizadas
    except Exception as e:
        logging.error(f"Erro crítico no Gemini: {e}")
        return {}

# --- ENVIO DE E-MAIL ---

def enviar_email_html(lista_noticias, destinatarios):
    if not destinatarios: return

    msg = EmailMessage()
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    msg['Subject'] = f'📌 Clipping Telecom & Audiovisual - {data_hoje}'
    msg['From'] = email_user
    msg['To'] = ", ".join(destinatarios)

    html_corpo = """<html><body style="font-family: Arial, sans-serif; color: #333;">
                    <h2 style="color: #0056b3; border-bottom: 2px solid #0056b3; padding-bottom: 10px;">
                    Relatório Diário: Telecom e Audiovisual</h2>"""

    categorias = [("TELECOM", "NOTÍCIAS TELECOM"), ("CINEMA", "NOTÍCIAS AUDIOVISUAL")]

    for chave_cat, titulo_cat in categorias:
        noticias_cat = {u: i for u, i in lista_noticias.items() if i.get('categoria') == chave_cat}
        if noticias_cat:
            html_corpo += f'<h3 style="background-color: #0056b3; color: #ffffff; padding: 10px; margin-top: 30px; border-radius: 4px;">{titulo_cat}</h3>'
            for url, item in noticias_cat.items():
                resumo_html = item.get('resumo', '<i>Resumo não gerado. Verifique os logs.</i>')
                html_corpo += f"""
                <div style="margin-bottom: 25px; padding: 15px; border-left: 5px solid #0056b3; background: #f9f9f9;">
                    <div style="margin-bottom: 10px;">
                        <span style="font-weight: bold;">[{item['fonte']}]</span>
                        <a href="{url}" style="color: #0056b3; text-decoration: none; font-weight: bold;">{item['titulo']}</a>
                    </div>
                    <div style="background: #fff; padding: 12px; border: 1px solid #ddd; border-radius: 4px;">
                        {resumo_html}
                    </div>
                </div>"""

    html_corpo += "</body></html>"
    msg.add_alternative(html_corpo, subtype='html')

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_user, email_pass)
            smtp.send_message(msg)
        print("E-mail enviado com sucesso!")
    except Exception as e: logging.error(f"Erro no envio do e-mail: {e}")

# --- EXECUÇÃO ---

emails = carregar_lista("email_destino.lista")
termos_telecom = carregar_lista("termos_chave_telecom.lista")
termos_cinema = carregar_lista("termos_chave_cinema.lista")

if termos_telecom or termos_cinema:
    noticias = buscar_clipping_inteligente(termos_telecom, termos_cinema)
    if noticias:
        noticias_com_resumo = processar_resumos_batch(noticias)
        if noticias_com_resumo:
            enviar_email_html(noticias_com_resumo, emails)
        else:
            print("Notícias encontradas, mas nenhuma passou pelo filtro da IA.")
    else:
        print("Nenhuma notícia nova encontrada no período.")
