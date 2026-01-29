import requests
from bs4 import BeautifulSoup
from google import genai
import time, os, smtplib, logging, sys
from datetime import datetime, timedelta
from email.message import EmailMessage

# Configuração de Log robusta para GitHub Actions
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("clipping.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# 1. Configurações de Ambiente
api_key = os.environ.get("GEMINI_API_KEY")
email_user = os.environ.get("EMAIL_USER")
email_pass = os.environ.get("EMAIL_PASS")

client = genai.Client(api_key=api_key)

# --- FUNÇÕES DE SUPORTE ---

def carregar_lista(nome_arquivo):
    """Carrega termos ou e-mails de arquivos externos."""
    if os.path.exists(nome_arquivo):
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            lista = [linha.strip() for linha in f if linha.strip()]
            logging.info(f"Arquivo {nome_arquivo} carregado com {len(lista)} itens.")
            return lista
    logging.warning(f"Arquivo {nome_arquivo} não encontrado.")
    return []

def extrair_data(soup_artigo):
    """Localiza a data de publicação para o filtro temporal."""
    data_tag = soup_artigo.find('meta', property='article:published_time')
    if data_tag:
        return datetime.fromisoformat(data_tag['content'].split('T')[0])
    time_tag = soup_artigo.find('time')
    if time_tag and time_tag.get('datetime'):
        return datetime.fromisoformat(time_tag['datetime'].split('T')[0])
    return None

def formatar_resumo_telecom(texto_retornado_ia):
    """Garante que o Outlook renderize as quebras de linha corretamente usando <div>."""
    if not texto_retornado_ia: return ""
    linhas = texto_retornado_ia.strip().split('\n')
    linhas_finalizadas = []
    
    substituicoes = {
        "Ação:": "<strong>Ação:</strong>", 
        "Impacto:": "<strong>Impacto:</strong>", 
        "Valores:": "<strong>Números:</strong>", 
        "Números:": "<strong>Números:</strong>"
    }

    for linha in linhas:
        linha = linha.strip()
        if not linha or any(x in linha.upper() for x in ["TÍTULO:", "RESUMO:", "URL:"]):
            continue
        
        encontrou_topico = False
        for original, negrito in substituicoes.items():
            if original in linha:
                linha = linha.replace(original, negrito)
                encontrou_topico = True
                break
        
        if encontrou_topico:
            linhas_finalizadas.append(f'<div style="margin-bottom: 8px; display: block;">{linha}</div>')
            
    return "".join(linhas_finalizadas)

# --- FUNÇÃO DE BUSCA E RASPAGEM ---

def buscar_clipping_inteligente(termos_telecom, termos_cinema):
    fontes_telecom = {
        "TeleTime": "https://teletime.com.br/?s=", 
        "TeleSíntese": "https://telesintese.com.br/?s=", 
        "MobileTime": "https://www.mobiletime.com.br/?s="
    }
    fontes_cinema = {
        "TelaViva": "https://telaviva.com.br/?s=",
        "PortalExibidor": "https://www.exibidor.com.br/?s=",
        "FilmeB": "https://www.filmeb.com.br/noticias?s="
    }

    noticias_filtradas = {}
    agora = datetime.now()
    # Janela de 72h para segundas-feiras, 24h para os demais dias
    horas_atras = 72 if agora.weekday() == 0 else 24
    limite_periodo = (agora - timedelta(hours=horas_atras)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    def executar_varredura(lista_fontes, lista_termos, categoria):
        for nome_fonte, url_base in lista_fontes.items():
            for termo in lista_termos:
                try:
                    res = requests.get(f"{url_base}{termo.replace(' ', '+')}", headers=headers, timeout=15)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    
                    # Seletores CSS específicos por site
                    if "filmeb.com.br" in url_base:
                        links = soup.select('div.noticias-lista h3 a, h3.post-title a, .views-field-title a')[:3]
                    elif "exibidor" in url_base:
                        links = soup.select('.noticia-item h2 a, .noticias-lista a')[:3]
                    elif "telaviva" in url_base:
                        links = soup.select('#main h2.entry-title a, #primary h2.entry-title a')[:5]
                    else:
                        links = soup.select('h2.entry-title a, h3.entry-title a')[:3]

                    for link in links:
                        url_artigo = link['href']
                        
                        # CORREÇÃO: Resolve URLs relativas (comum no FilmeB)
                        if url_artigo.startswith('/'):
                            dominio = "https://" + url_base.split('/')[2]
                            url_artigo = dominio + url_artigo

                        # Filtro contra links institucionais
                        if any(sujo in url_artigo.lower() for sujo in ['quem-somos', 'anuncie', 'contato', 'expediente']):
                            continue
                        
                        if url_artigo not in noticias_filtradas:
                            res_art = requests.get(url_artigo, headers=headers, timeout=10)
                            soup_art = BeautifulSoup(res_art.text, 'html.parser')
                            data_pub = extrair_data(soup_art)
                            
                            if data_pub and data_pub >= limite_periodo:
                                p = soup_art.find_all('p')
                                texto = " ".join([item.text for item in p[:5]])
                                if len(texto) > 100:
                                    noticias_filtradas[url_artigo] = {
                                        "titulo": link.get_text().strip(), 
                                        "fonte": nome_fonte, 
                                        "categoria": categoria, 
                                        "texto": texto,
                                        "termo": termo
                                    }
                except Exception as e:
                    logging.error(f"Erro na fonte {nome_fonte} (Termo: {termo}): {e}")
    
    # Executa as buscas separadamente para otimizar tempo
    executar_varredura(fontes_telecom, termos_telecom, "TELECOM")
    executar_varredura(fontes_cinema, termos_cinema, "CINEMA")
    return noticias_filtradas

# --- PROCESSAMENTO COM GEMINI IA ---

def processar_resumos_batch(dict_noticias):
    if not dict_noticias: return {}
    
    prompt = (
        "Você é um Analista de Mercado Sênior especializado em Telecomunicações e Indústria Audiovisual.\n"
        "Sua tarefa é criar resumos técnicos baseados no conteúdo fornecido.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Para cada notícia, gere um resumo com exatamente 3 campos: Ação:, Impacto: e Valores:.\n"
        "2. IMPORTANTE: Use o separador '---' estritamente entre os resumos de notícias diferentes.\n"
        "3. Se a notícia for irrelevante ao setor de infraestrutura, telecom ou cinema, responda 'DESCARTAR'.\n"
        "4. Não use negritos ou markdown.\n\n"
    )
    
    links_ordenados = list(dict_noticias.keys())
    for url in links_ordenados:
        prompt += f"TÍTULO: {dict_noticias[url]['titulo']}\nCONTEÚDO: {dict_noticias[url]['texto']}\n\n---\n\n"
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        # Limpeza para evitar falhas de split
        resumos = [r.strip() for r in response.text.split("---") if len(r.strip()) > 5]
        
        finalizadas = {}
        for i, resumo in enumerate(resumos):
            if i < len(links_ordenados):
                url = links_ordenados[i]
                if "DESCARTAR" not in resumo.upper():
                    dict_noticias[url]['resumo'] = formatar_resumo_telecom(resumo)
                    finalizadas[url] = dict_noticias[url]
        return finalizadas
    except Exception as e:
        logging.error(f"Erro no Gemini: {e}")
        return {}

# --- FORMATAÇÃO E ENVIO DE E-MAIL ---

def enviar_email_html(lista_noticias, destinatarios):
    if not destinatarios: return
    msg = EmailMessage()
    msg['Subject'] = f'📌 Clipping Telecom & Audiovisual - {datetime.now().strftime("%d/%m/%Y")}'
    msg['From'] = email_user
    msg['To'] = ", ".join(destinatarios)
    
    html = '<html><body style="font-family: Arial, sans-serif; color: #333;">'
    html += '<h2 style="color: #0056b3; border-bottom: 2px solid #0056b3; padding-bottom: 10px;">Relatório Diário</h2>'
    
    # Organização por Seções no E-mail
    secoes = [("TELECOM", "NOTÍCIAS TELECOM"), ("CINEMA", "NOTÍCIAS AUDIOVISUAL")]
    
    for chave_cat, titulo_cat in secoes:
        noticias_cat = {u: i for u, i in lista_noticias.items() if i.get('categoria') == chave_cat}
        if noticias_cat:
            html += f'<h3 style="background:#0056b3;color:#fff;padding:10px;border-radius:4px;margin-top:30px;">{titulo_cat}</h3>'
            for url, item in noticias_cat.items():
                html += f"""
                <div style="margin-bottom:20px;padding:15px;border-left:5px solid #0056b3;background:#f9f9f9;">
                    <div style="margin-bottom:10px;">
                        <span style="font-weight: bold;">[{item['fonte']}]</span> 
                        <a href="{url}" style="color:#0056b3;text-decoration:none;font-weight:bold;">{item['titulo']}</a>
                    </div>
                    <div style="background:#fff;padding:12px;border:1px solid #ddd;border-radius:4px;">
                        {item.get('resumo', '<i>Resumo indisponível.</i>')}
                    </div>
                </div>"""
                
    html += '</body></html>'
    msg.add_alternative(html, subtype='html')
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_user, email_pass)
            smtp.send_message(msg)
        logging.info("E-mail enviado com sucesso!")
    except Exception as e:
        logging.error(f"Falha no envio do e-mail: {e}")

# --- EXECUÇÃO PRINCIPAL ---

if __name__ == "__main__":
    logging.info("Iniciando processamento do Clipping...")
    
    destinos = carregar_lista("email_destino.lista")
    t_telecom = carregar_lista("termos_chave_telecom.lista")
    t_cinema = carregar_lista("termos_chave_cinema.lista")

    if not destinos:
        logging.error("Interrompido: Ninguém para receber o e-mail.")
    elif not t_telecom and not t_cinema:
        logging.error("Interrompido: Listas de termos estão vazias.")
    else:
        # 1. Busca as notícias
        resultado = buscar_clipping_inteligente(t_telecom, t_cinema)
        
        if resultado:
            logging.info(f"{len(resultado)} notícias capturadas. Enviando para IA...")
            # 2. Gera os resumos via Gemini
            noticias_com_resumo = processar_resumos_batch(resultado)
            
            if noticias_com_resumo:
                # 3. Envia o relatório final
                enviar_email_html(noticias_com_resumo, destinos)
            else:
                logging.warning("Nenhuma notícia passou pelo filtro de relevância da IA.")
        else:
            logging.info("Nenhuma notícia nova encontrada para os termos monitorados.")
