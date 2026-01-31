import requests
from bs4 import BeautifulSoup
from google import genai
import time, os, logging, sys, re
from datetime import datetime, timedelta

# Configuração de Log (Mantendo o seu padrão detalhado com checkpoints)
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
resend_api_key = os.environ.get("EMAIL_PASS")  # Deve ser a API Key do Resend (re_...)
email_remetente = "clipping@otavioroma.com.br"  # Domínio otavioroma.com.br já verificado

client = genai.Client(api_key=api_key)

# --- FUNÇÕES DE SUPORTE ---

def carregar_lista(nome_arquivo):
    if os.path.exists(nome_arquivo):
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            # Filtra linhas vazias e ignora linhas que começam com #
            return [linha.strip() for linha in f if linha.strip() and not linha.strip().startswith('#')]
    return []

def extrair_data(soup_artigo):
    """Extrai e converte datas, com lógica específica para o FilmeB e portais de telecom"""
    data_tag = soup_artigo.find('meta', property='article:published_time')
    if data_tag:
        try: return datetime.fromisoformat(data_tag['content'].split('T')[0])
        except: pass

    texto_pagina = soup_artigo.get_text().lower()
    meses = {
        'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
        'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12
    }

    match_texto = re.search(r'(\d{1,2})\s+([a-z]{3})\s+(\d{2,4})', texto_pagina)
    if match_texto:
        dia = int(match_texto.group(1))
        mes_str = match_texto.group(2)
        ano_bruto = match_texto.group(3)
        ano = int(ano_bruto) + 2000 if len(ano_bruto) == 2 else int(ano_bruto)
        if mes_str in meses:
            try: return datetime(ano, meses[mes_str], dia)
            except: pass

    match_num = re.search(r'(\d{2})/(\d{2})/(\d{4})', texto_pagina)
    if match_num:
        try: return datetime.strptime(match_num.group(0), '%d/%m/%Y')
        except: pass
    return None

def formatar_resumo_html(texto_ia):
    if not texto_ia: return ""
    linhas = texto_ia.strip().split('\n')
    linhas_finalizadas = []
    
    substituicoes = {
        "Ação:": "<strong>Ação:</strong>", 
        "Impacto:": "<strong>Impacto:</strong>", 
        "Números:": "<strong>Números:</strong>"
    }

    for linha in linhas:
        linha = linha.strip()
        if not linha or any(x in linha.upper() for x in ["TÍTULO:", "RESUMO:", "URL:"]):
            continue
        for original, negrito in substituicoes.items():
            if original in linha:
                linha = linha.replace(original, negrito)
                break
        linhas_finalizadas.append(f'<div style="margin-bottom: 8px; display: block;">{linha}</div>')
    return "".join(linhas_finalizadas)

# --- FUNÇÃO DE BUSCA ---

def buscar_clipping_inteligente(termos_telecom, termos_cinema):
    fontes_telecom = {"TeleTime": "https://teletime.com.br/?s=", "TeleSíntese": "https://telesintese.com.br/?s=", "MobileTime": "https://www.mobiletime.com.br/?s="}
    fontes_cinema = {"TelaViva": "https://telaviva.com.br/?s=", "FilmeB": "https://www.filmeb.com.br/noticias?s="}

    noticias_filtradas = {}
    agora = datetime.now()
    horas_atras = 72 if agora.weekday() == 0 else 24
    limite_periodo = (agora - timedelta(hours=horas_atras)).replace(hour=0, minute=0, second=0, microsecond=0)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    def executar_varredura(lista_fontes, lista_termos, categoria):
        for nome_fonte, url_base in lista_fontes.items():
            for termo in lista_termos:
                try:
                    res = requests.get(f"{url_base}{termo.replace(' ', '+')}", headers=headers, timeout=15)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    
                    if "filmeb" in url_base:
                        links = soup.select('div.noticias-lista h3 a, h3.post-title a, .views-field-title a')[:5]
                    else:
                        links = soup.select('h2.entry-title a, h3.entry-title a, #main h2 a')[:3]

                    for link in links:
                        url_artigo = link['href']
                        if url_artigo.startswith('/'):
                            dominio_base = "https://www.filmeb.com.br" if "filmeb" in url_base else "https://" + url_base.split('/')[2]
                            url_artigo = dominio_base + url_artigo

                        if any(sujo in url_artigo.lower() for sujo in ['quem-somos', 'anuncie', 'contato']): continue
                        
                        if url_artigo not in noticias_filtradas:
                            res_art = requests.get(url_artigo, headers=headers, timeout=10)
                            soup_art = BeautifulSoup(res_art.text, 'html.parser')
                            data_pub = extrair_data(soup_art)
                            
                            if data_pub and data_pub >= limite_periodo:
                                corpo = soup_art.select_one('.field-name-body')
                                texto = corpo.get_text(separator=' ', strip=True) if corpo else " ".join([item.text for item in soup_art.find_all('p')[:5]])

                                if len(texto) > 100:
                                    noticias_filtradas[url_artigo] = {"titulo": link.get_text().strip(), "fonte": nome_fonte, "categoria": categoria, "texto": texto[:1500]}
                            else:
                                logging.info(f"PULADA (Data inválida/antiga): {url_artigo}")
                    time.sleep(0.5)
                except Exception as e:
                    logging.error(f"Erro em {nome_fonte} ({termo}): {e}")
    
    executar_varredura(fontes_telecom, termos_telecom, "TELECOM")
    executar_varredura(fontes_cinema, termos_cinema, "CINEMA")
    return noticias_filtradas

# --- IA E E-MAIL ---

def processar_resumos_batch(dict_noticias):
    if not dict_noticias: return {}
    prompt = (
        "Atue como um Analista de Mercado Sênior especializado em Telecomunicações e Indústria Audiovisual.\n"
        "Sua tarefa é criar resumos técnicos e aprofundados baseados no conteúdo fornecido.\n\n"
        "REGRAS CRÍTICAS DE EXECUÇÃO:\n"
        "1. Para cada notícia, gere obrigatoriamente um resumo com 3 campos: Ação:, Impacto: e Números:.\n"
        "2. IMPORTANTE: Utilize o separador '---' (três hífens) estritamente entre os resumos de notícias diferentes.\n"
        "3. Se a notícia for irrelevante ao setor de data center, telecom, mercado audiovisual ou TI, responda apenas 'DESCARTAR'.\n"
        "4. Mantenha um tom profissional. Não utilize negritos Markdown.\n\n"
    )
    links = list(dict_noticias.keys())
    for url in links:
        prompt += f"TÍTULO: {dict_noticias[url]['titulo']}\nCONTEÚDO: {dict_noticias[url]['texto']}\n\n---\n\n"
    
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        resumos = [r.strip() for r in response.text.split("---") if len(r.strip()) > 5]
        finalizadas = {}
        for i, resumo in enumerate(resumos):
            if i < len(links) and "DESCARTAR" not in resumo.upper():
                url = links[i]
                dict_noticias[url]['resumo'] = formatar_resumo_html(resumo)
                finalizadas[url] = dict_noticias[url]
        return finalizadas
    except Exception as e:
        logging.error(f"Erro Gemini: {e}")
        return {}

def enviar_email(lista_noticias, destinatarios):
    if not destinatarios or not resend_api_key:
        logging.error("Dados ausentes: Verifique destinatários ou EMAIL_PASS (Resend Key).")
        return

    assunto = f'📌 Clipping Telecom & Audiovisual - {datetime.now().strftime("%d/%m/%Y")}'
    
    html = '<html><body style="font-family: Arial, sans-serif; color: #333;">'
    html += f'<h2 style="color: #0056b3; border-bottom: 2px solid #0056b3; padding-bottom: 10px;">Clipping Diário - {datetime.now().strftime("%d/%m/%Y")}</h2>'
    
    for cat_chave, cat_nome in [("TELECOM", "TELECOM"), ("CINEMA", "AUDIOVISUAL")]:
        noticias_cat = {u: i for u, i in lista_noticias.items() if i.get('categoria') == cat_chave}
        if noticias_cat:
            html += f'<h3 style="background:#0056b3;color:#fff;padding:10px;margin-top:20px;border-radius:3px;">{cat_nome}</h3>'
            for url, item in noticias_cat.items():
                html += f'<div style="margin-bottom:20px;padding:15px;background:#fdfdfd;border:1px solid #eee;border-left:5px solid #0056b3;">'
                html += f'<b style="color:#0056b3;">[{item["fonte"]}]</b> <a href="{url}" style="text-decoration:none;color:#333;font-weight:bold;font-size:16px;">{item["titulo"]}</a><br><br>'
                html += f'<div style="font-size:14px;line-height:1.5;color:#444;">{item.get("resumo", "")}</div></div>'
    
    html += '<p style="font-size:12px;color:#999;margin-top:30px;">Gerado automaticamente para Otavio Scheidegger via Gemini IA & Resend.</p>'
    html += '</body></html>'

    try:
        url_resend = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "from": f"Clipping Telecom <{email_remetente}>",
            "to": destinatarios,
            "subject": assunto,
            "html": html
        }

        response = requests.post(url_resend, json=payload, headers=headers)
        
        if response.status_code in [200, 201]:
            logging.info(f"E-mail enviado com sucesso! ID: {response.json().get('id')}")
        else:
            logging.error(f"Falha no Resend: {response.status_code} - {response.text}")

    except Exception as e:
        logging.error(f"Erro de conexão ao enviar para o Resend: {e}")

if __name__ == "__main__":
    logging.info("=== INICIANDO PROCESSO DE CLIPPING ===")
    
    # Checkpoint: Leitura de arquivos
    emails = carregar_lista("email_destino.lista")
    t_telecom = carregar_lista("termos_chave_telecom.lista")
    t_cinema = carregar_lista("termos_chave_cinema.lista")
    
    logging.info(f"Arquivos lidos. Emails: {len(emails)}, Telecom: {len(t_telecom)}, Cinema: {len(t_cinema)}")

    if emails and (t_telecom or t_cinema):
        logging.info("Iniciando busca inteligente nas fontes de notícias...")
        resultado = buscar_clipping_inteligente(t_telecom, t_cinema)
        
        if resultado:
            logging.info(f"{len(resultado)} notícias potenciais encontradas. Gerando resumos com Gemini...")
            final = processar_resumos_batch(resultado)
            
            if final: 
                logging.info(f"IA concluiu resumos de {len(final)} notícias relevantes. Disparando e-mail...")
                enviar_email(final, emails)
            else:
                logging.warning("A IA descartou todas as notícias como irrelevantes para o setor.")
        else:
            logging.info("Nenhuma notícia encontrada com os termos informados nas últimas 24/72h.")
    else:
        logging.error("Finalizado: Arquivos de configuração vazios ou ausentes.")
    
    logging.info("=== FIM DO PROCESSO ===")
