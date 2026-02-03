# 📌 Clipping Automático Telecom & Audiovisual

## 📖 Visão Geral
Este projeto é uma ferramenta de automação em Python desenvolvida para **Otavio Scheidegger**. O objetivo é realizar web scraping inteligente em portais especializados, processar o conteúdo via IA para gerar resumos executivos e distribuir o resultado por e-mail.

## 🛠️ Stack Tecnológica
- **Linguagem:** Python 3.12+.
- **IA:** Gemini 2.0 Flash (via Google GenAI SDK).
- **Web Scraping:** BeautifulSoup4 e Requests.
- **Envio de E-mail:** Resend API.
- **Infraestrutura:** GitHub Actions (Execução agendada).

## ⚙️ Configurações Críticas
- **Remetente Oficial:** `clipping_ai_detic@otavioroma.com.br`.
- **E-mail de Contingência:** `otavioroma@gmail.com` (usado para alertas quando não há notícias).
- **Timeouts:** Máximo de **5 segundos** por requisição para evitar travamentos no ambiente de CI/CD.
- **Logging:** Configurado como `PYTHONUNBUFFERED` para exibição em tempo real no console do GitHub.

## 📂 Estrutura de Arquivos de Dados
O script depende da leitura de três arquivos de texto simples (.lista):
1. `email_destino.lista`: Lista de destinatários do clipping.
2. `termos_chave_telecom.lista`: Termos de busca para o setor de telecomunicações.
3. `termos_chave_cinema.lista`: Termos de busca para a indústria audiovisual.

## 📝 Regras para a IA (Codex/Cline)
1. **Padrão de Código:** Sempre utilize `logging` em vez de `print`.
2. **Resiliência:** Sempre implemente blocos `try-except` em funções de scraping para evitar que falhas em um site parem o processo todo.
3. **Estilo de Resumo:** Os resumos gerados pela IA devem conter obrigatoriamente os campos Ação:, Impacto: e Números:. JAMAIS altere o texto do prompt.
4. **Localização:** O script deve considerar o fuso horário de Brasília para o filtro de datas das notícias.