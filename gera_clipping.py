import requests
from bs4 import BeautifulSoup
from google import genai
import time, os, smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
import logging

# Configura o log para salvar em 'clipping.log'
logging.basicConfig(
    filename='clipping.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

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
    fontes = {
        "TeleTime": "https://teletime.com.br/?s=", 
        "TeleSíntese": "https://telesintese.com.br/?s=",
        "MobileTime": "https://www.mobiletime.com.br/?s=",
        "TelaViva": "https://telaviva.com.br/?s=",
        "PortalExibidor": "https://www.exibidor.com.br/?s=",
        "FilmeB": "https://www.filmeb.com.br/?s="
    }
    noticias_filtradas = {}
    
    agora = datetime.now()
    horas_atras = 72 if agora.weekday() == 0 else 24
    limite_periodo = (agora - timedelta(hours=horas_atras)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    print(f"Iniciando busca. Janela: {horas_atras} horas.")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    for nome_fonte, url_base in fontes.items():
        for termo in termos:
            termo_url = termo.replace(' ', '+').replace('"', '')
            try:
                # O bloco abaixo deve estar indentado para dentro do 'try'
                res = requests.get(f"{url_base}{termo_url}", headers=headers, timeout=15)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 1. Seleção dos links por fonte
                if "filmeb" in url_base:
                    links = soup.select('div.noticias-lista h3 a, .post-title a')[:3]
                elif "exibidor" in url_base:
                    links = soup.select('.noticia-item h2 a, .noticias-lista a')[:3]
                else:
                    links = soup.select('h2.entry-title a, h3.entry-title a')[:3]

                # 2. O loop de links deve ficar fora dos 'ifs' para processar todas as fontes
                for link in links:
                    url_artigo = link['href']
                    logging.info(f"Termo: [{termo}] | Link capturado: {url_artigo}")
                    
                    if url_artigo not in noticias_filtradas:
                        res_art = requests.get(url_artigo, headers=headers, timeout=10)
                        soup_art = BeautifulSoup(res_art.text, 'html.parser')
                        data_pub = extrair_data(soup_art)

                        if data_pub and data_pub >= limite_periodo:
                            paragrafos = soup_art.find_all('p')
                            noticias_filtradas[url_artigo] = {
                                "titulo": link.get_text().strip(),
                                "fonte": nome_fonte,
                                "termo": termo,
                                "texto": " ".join([p.text for p in paragrafos[:4]])
                            }
                        else:
                            logging.warning(f"Link descartado por DATA ({data_pub}): {url_artigo}")
                
                time.sleep(0.5)
            except Exception as e:
                logging.error(f"Erro ao buscar na fonte {nome_fonte}: {e}")
                continue

    return noticias_filtradas

def processar_resumos_batch(dict_noticias):
    if not dict_noticias: return None
    
    # Novo prompt com persona de analista e instrução de descarte
    prompt = (
    "Você é um Analista de Mercado especializado em Telecomunicações, Tecnologia da Informação e Indústria Audiovisual.\n"
    "Sua tarefa é resumir notícias sobre infraestrutura digital, conectividade, mercado de cinema e exibição.\n\n"
    "REGRAS CRÍTICAS:\n"
    "1. ACEITE apenas notícias sobre: operadoras, data centers, políticas de telecom, mercado exibidor (salas de cinema), "
    "produção audiovisual, streaming ou tecnologias de projeção/som. Se for fora disso, responda 'DESCARTAR'.\n"
    "2. Se for relevante, resuma em 3 pontos: (Ação | Impacto | Valores).\n"
    "3. RESTRIÇÃO DE FORMATAÇÃO: Não utilize negrito (**) ou Markdown. Use apenas texto puro.\n"
    "4. Separe os resumos de cada notícia com '---'.\n\n"
)
    
    links_ordenados = list(dict_noticias.keys())
    for url in links_ordenados:
        prompt += f"TÍTULO: {dict_noticias[url]['titulo']}\nCONTEÚDO: {dict_noticias[url]['texto']}\n\n---\n\n"

    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        resumos = response.text.split("---")
        
        noticias_filtradas = {}
        
        # Itera sobre os resumos gerados e verifica o descarte
        for i, resumo_bruto in enumerate(resumos):
            if i < len(links_ordenados):
                url = links_ordenados[i]
                conteudo = resumo_bruto.strip()
                
                # Se a IA não descartou, adicionamos ao dicionário final
                if "DESCARTAR" not in conteudo.upper():
                    resumo_formatado = formatar_resumo_telecom(conteudo) #formata o HTML antes de salvar
                    dict_noticias[url]['resumo'] = resumo_formatado
                    noticias_filtradas[url] = dict_noticias[url]
                else:
                    logging.warning(f"IA descartou o conteúdo por irrelevância: {url}") # LOG AQUI
        
        return noticias_filtradas
    except Exception as e:
        print(f"Erro no processamento IA: {e}")
        # Em caso de erro, retorna o dicionário original para não perder as notícias
        return dict_noticias
        
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
            <div style="margin-bottom: 10px;">
                <span style="font-weight: bold; color: #333;">[{fonte}]</span>
                <a href="{url}" style="color: #0056b3; text-decoration: none; font-weight: bold; font-size: 16px;">{titulo}</a>
            </div>
            <div style="background: #fff; padding: 12px; border: 1px solid #ddd; border-radius: 4px; font-family: Arial, sans-serif;">
                {resumo}
            </div>
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

def formatar_resumo_telecom(texto_retornado_ia):
    # Divide o texto em linhas para processamento individual
    linhas = texto_retornado_ia.strip().split('\n')
    if not linhas: return ""

    linhas_finalizadas = []
    
    for linha in linhas:
        linha = linha.strip()
        if not linha: continue
        
        # Ignora a linha que contém o título repetido
        if linha.upper().startswith("TÍTULO:"):
            continue

        # Dicionário de limpeza e formatação dos rótulos
        substituicoes = {
            "1. Ação:": "<strong>Ação:</strong>",
            "2. Impacto:": "<strong>Impacto:</strong>",
            "3. Valores:": "<strong>Números:</strong>",
            "Ação:": "<strong>Ação:</strong>",
            "Impacto:": "<strong>Impacto:</strong>",
            "Valores:": "<strong>Números:</strong>"
        }
        
        encontrou_topico = False
        for original, negrito in substituicoes.items():
            if original in linha:
                linha = linha.replace(original, negrito)
                encontrou_topico = True
                break
        
        # Se for um tópico (Ação, Impacto ou Valores), encapsula em um <div>
        # O style margin-bottom garante o respiro visual entre as linhas
        if encontrou_topico:
            linhas_finalizadas.append(f'<div style="margin-bottom: 8px; display: block;">{linha}</div>')

    return "".join(linhas_finalizadas)
    
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
