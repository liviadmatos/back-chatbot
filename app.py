from flask import Flask, request, session, jsonify
from flask_socketio import SocketIO, emit
from google import genai
from google.genai import types
from dotenv import load_dotenv
from uuid import uuid4
import os

# Carrega as variáveis ocultas do arquivo .env (como a chave da API do Gemini)
load_dotenv()

# Define qual versão da IA vamos usar. O modelo "flash" é rápido e ideal para chatbots.
MODELO = "gemini-2.5-flash"

# Aqui definimos o "Prompt de Sistema". É a personalidade e as regras que o bot deve seguir.
instrucoes = """
Você é Aurora, uma assistente virtual de apoio emocional e bem-estar.

IDENTIDADE E OBJETIVO:
Seu objetivo é oferecer escuta acolhedora, apoio emocional leve, organização de pensamentos e incentivo a hábitos saudáveis. Você NÃO substitui psicólogos, psiquiatras, terapia, emergência médica ou ajuda profissional.

Você ajuda o usuário a:
- desabafar
- organizar pensamentos e emoções
- refletir sobre situações pessoais
- lidar com estresse, ansiedade leve, tristeza, conflitos e inseguranças
- desenvolver autoconhecimento
- criar hábitos saudáveis de sono, estudos, alimentação e rotina
- praticar exercícios simples de regulação emocional

FORMA DE FALAR:
- Seja acolhedora, gentil, respeitosa e calma.
- Fale de forma humana e natural.
- Nunca seja fria, robótica ou excessivamente formal.
- Nunca julgue, ridicularize ou minimize sentimentos.
- Evite frases clichês excessivas.
- Evite soar paternalista.
- Demonstre empatia sem fingir emoções humanas.
- Faça perguntas abertas quando apropriado.
- Responda de forma curta a moderada (evite textos enormes sem necessidade).

COMO TRATAR O USUÁRIO:
- Valide emoções sem assumir fatos.
- Evite conclusões precipitadas.
- Não pressione o usuário.
- Incentive reflexão.
- Respeite silêncio, confusão e ambivalência.
- Nunca culpabilize o usuário.
- Não imponha decisões.

EXEMPLOS DE TOM:
Usuário: "Estou muito mal."
Resposta:
"Sinto muito que esteja sendo um momento difícil. Quer me contar o que aconteceu ou o que está pesando mais agora?"

Usuário: "Briguei com minha amiga."
Resposta:
"Brigas podem mexer bastante com a gente. O que aconteceu entre vocês?"

LIMITES IMPORTANTES:
Você NÃO deve:
- diagnosticar transtornos mentais
- afirmar que alguém tem depressão, ansiedade, TDAH etc.
- substituir ajuda profissional
- afirmar certezas psicológicas
- manipular emocionalmente
- incentivar dependência emocional do chatbot
- agir como médico, terapeuta licenciado ou psiquiatra

SE O USUÁRIO PEDIR DIAGNÓSTICO:
Explique de forma cuidadosa:
“Posso ajudar você a refletir sobre sintomas e sentimentos, mas não posso diagnosticar condições. Um profissional qualificado consegue avaliar isso adequadamente.”

SE O USUÁRIO FALAR DE ASSUNTOS FORA DO CONTEXTO:
Você pode conversar brevemente, mas deve gentilmente redirecionar ao propósito principal.

Exemplo:
Usuário: “Qual o melhor celular?”
Resposta:
“Posso conversar sobre isso também 😊 Mas meu foco principal é apoio emocional e bem-estar. Sobre celulares, o que você procura?”

Usuário: “Faz minha lição de matemática.”
Resposta:
“Posso tentar ajudar rapidamente, mas fui criada principalmente para conversas de apoio emocional e organização dos pensamentos.”

SITUAÇÕES DE SOFRIMENTO EMOCIONAL:
Se o usuário demonstrar tristeza, ansiedade, solidão, medo ou estresse:
1. acolha
2. faça perguntas abertas
3. ajude a organizar pensamentos
4. sugira estratégias leves quando fizer sentido
5. nunca minimize sentimentos

EXEMPLO:
“Isso parece estar pesando bastante em você. O que você acha que está sendo a parte mais difícil dessa situação?”

SE HOUVER RISCO OU FALA DE AUTOAGRESSÃO:
Leve sempre a sério.
- mantenha tom acolhedor
- incentive procurar alguém de confiança
- incentive ajuda profissional ou emergência local
- pergunte se a pessoa está segura naquele momento
- nunca incentive autolesão
- nunca normalize suicídio

Exemplo:
“Obrigado por me contar isso. Parece algo muito pesado para carregar sozinho(a). Estou preocupado(a) com sua segurança. Você está em segurança agora? Existe alguém de confiança com quem possa falar hoje?”

PERSONALIDADE:
- acolhedora
- calma
- respeitosa
- inteligente
- gentil sem exageros
- empática, mas equilibrada
- conversa como alguém maduro e confiável

REGRA FINAL:
Seu foco principal é apoio emocional, autoconhecimento e bem-estar. Quando outros assuntos surgirem, converse brevemente se necessário, mas sem perder sua identidade principal.Sempre volte ao emocional da pessoa, independente do assunto, dizendo que é um chat de terapia e nao tem informações sobre o restante das coisas.
"""

# Inicializa a conexão com a inteligência artificial do Google usando a chave da API
client = genai.Client(api_key=os.getenv("GENAI_KEY"))

# Cria o nosso aplicativo web principal (o servidor)
app = Flask(__name__)

# A 'secret_key' funciona como uma senha interna do servidor para proteger 
# e criptografar os dados da sessão (as "lembranças" de quem é quem).
app.secret_key = "ch@tb07"

# Adiciona a funcionalidade de WebSockets (comunicação em tempo real) ao nosso app.
# O 'cors_allowed_origins="*"' é crucial: ele permite que o nosso front-end (HTML/JS) 
# consiga se conectar com esse back-end, mesmo que estejam em arquivos ou portas diferentes.
socketio = SocketIO(app, cors_allowed_origins="*")

# Dicionário que funciona como a "memória temporária" do servidor. 
# Ele guarda a conversa de cada aluno separadamente usando um ID único.
active_chats = {}

def get_user_chat():
    """
    Função principal de gerenciamento de usuários.
    Ela verifica quem está mandando a mensagem e recupera a conversa correta,
    garantindo que o bot não misture o chat do Aluno A com o do Aluno B.
    """
    
    # Passo 1: Se o usuário é novo (não tem um 'session_id'), criamos um ID único para ele.
    # Usamos o 'uuid4' para gerar um código aleatório impossível de repetir.
    if 'session_id' not in session:
        session['session_id'] = str(uuid4())
        print(f"Nova sessão Flask criada: {session['session_id']}")

    session_id = session['session_id']

    # Passo 2: Se o usuário já tem um ID, mas ainda não tem uma conversa aberta com o Gemini...
    if session_id not in active_chats:
        print(f"Criando novo chat Gemini para session_id: {session_id}")
        try:
            # ...nós criamos uma nova conversa e passamos as instruções (personalidade).
            chat_session = client.chats.create(
                model=MODELO,
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            # Guardamos essa conversa no nosso dicionário (memória).
            active_chats[session_id] = chat_session
            print(f"Novo chat Gemini criado e armazenado para {session_id}")
        except Exception as e:
            app.logger.error(f"Erro ao criar chat Gemini para {session_id}: {e}", exc_info=True)
            raise  # Se der erro aqui, repassa para o sistema avisar que falhou
    
    # Passo 3: Segurança extra. Se o servidor reiniciou (apagou a variável active_chats), 
    # mas o usuário ainda estava no navegador com o mesmo ID, nós recriamos a conexão dele.
    if session_id in active_chats and active_chats[session_id] is None:
        print(f"Recriando chat Gemini para session_id existente (estava None): {session_id}")
        try:
            chat_session = client.chats.create(
                model=MODELO,
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            active_chats[session_id] = chat_session
        except Exception as e:
            app.logger.error(f"Erro ao recriar chat Gemini para {session_id}: {e}", exc_info=True)
            raise

    # Retorna o histórico de mensagens exato daquele usuário.
    return active_chats[session_id]

# Rota simples para verificar se o servidor está rodando.
# Ao acessar o localhost no navegador, o aluno verá este aviso em formato JSON.
@app.route('/')
def root():
    return jsonify({
        "api-websocket": "chatbot",
        "status": "ok"
    })


# ------------------------------------------------------------------
# EVENTOS SOCKET.IO (Onde a mágica do tempo real acontece)
# ------------------------------------------------------------------

@socketio.on('connect')
def handle_connect():
    """
    EVENTO: Disparado no momento exato em que o Front-end (navegador) se conecta ao servidor.
    """
    print(f"Cliente conectado: {request.sid}")
    
    try:
        # Tenta criar a pasta do usuário assim que ele entra
        get_user_chat()
        user_session_id = session.get('session_id', 'N/A')
        print(f"Sessão Flask para {request.sid} usa session_id: {user_session_id}")
        
        # O comando 'emit' serve para enviar um pacote de dados do servidor PARA o front-end.
        emit('status_conexao', {'data': 'Conectado com sucesso!', 'session_id': user_session_id})
    except Exception as e:
        app.logger.error(f"Erro durante o evento connect para {request.sid}: {e}", exc_info=True)
        emit('erro', {'erro': 'Falha ao inicializar a sessão de chat no servidor.'})


@socketio.on('enviar_mensagem')
def handle_enviar_mensagem(data):
    """
    EVENTO: O Front-end mandou uma mensagem (ex: o usuário clicou em 'Enviar' no chat).
    A variável 'data' traz os dados enviados pelo HTML (o texto que o usuário digitou).
    """
    try:
        # Pega o texto de dentro do dicionário enviado pelo JS
        mensagem_usuario = data.get("mensagem")
        app.logger.info(f"Mensagem recebida de {session.get('session_id', request.sid)}: {mensagem_usuario}")

        # Validação básica: não deixa enviar mensagens vazias
        if not mensagem_usuario:
            emit('erro', {"erro": "Mensagem não pode ser vazia."})
            return

        # Puxa o histórico de conversa desse aluno específico
        user_chat = get_user_chat()
        if user_chat is None:
            emit('erro', {"erro": "Sessão de chat não pôde ser estabelecida."})
            return

        # ==========================================
        # COMUNICAÇÃO COM O GOOGLE GEMINI
        # ==========================================
        # Aqui o nosso servidor repassa a pergunta para a IA do Google...
        resposta_gemini = user_chat.send_message(mensagem_usuario)

        # ... e aqui extraímos apenas o texto da resposta que o Gemini devolveu.
        # (O 'if/else' garante que vamos achar o texto independente de como a API estruturar a resposta)
        resposta_texto = (
            resposta_gemini.text
            if hasattr(resposta_gemini, 'text')
            else resposta_gemini.candidates[0].content.parts[0].text
        )
        
        # O servidor usa o 'emit' para devolver a resposta final do bot lá para a tela do Front-end.
        emit('nova_mensagem', {"remetente": "bot", "texto": resposta_texto, "session_id": session.get('session_id')})
        app.logger.info(f"Resposta enviada para {session.get('session_id', request.sid)}: {resposta_texto}")

    except Exception as e:
        app.logger.error(f"Erro ao processar 'enviar_mensagem' para {session.get('session_id', request.sid)}: {e}", exc_info=True)
        # Se algo quebrar (ex: falha de internet), avisamos o front-end educadamente.
        emit('erro', {"erro": f"Ocorreu um erro no servidor: {str(e)}"})


@socketio.on('disconnect')
def handle_disconnect():
    """
    EVENTO: Disparado quando o usuário fecha a aba do navegador ou perde a conexão.
    """
    print(f"Cliente desconectado: {request.sid}, session_id: {session.get('session_id', 'N/A')}")


# Inicia o servidor local. A porta padrão do Flask costuma ser a 5000.
if __name__ == "__main__":
    socketio.run(app)