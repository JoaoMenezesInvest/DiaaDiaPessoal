import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json
from google.oauth2 import service_account
import bcrypt
from datetime import datetime

# Configuração da página
st.set_page_config(layout="wide", page_title="Meu Diário Pessoal")

# Função para inicializar o Firebase
def init_firebase():
    """Inicializa a conexão com o Firebase usando credenciais do Streamlit Secrets ou de um arquivo local."""
    if firebase_admin._apps:
        return firestore.client()
    
    try:
        # Tenta carregar as credenciais do Streamlit Secrets (para deploy)
        key_dict = json.loads(st.secrets["FIREBASE_SERVICE_ACCOUNT_KEY"])
        creds = service_account.Credentials.from_service_account_info(key_dict)
        firebase_admin.initialize_app(creds)
    except (KeyError, json.JSONDecodeError):
        # Se falhar, tenta carregar do arquivo local (para rodar no seu PC)
        try:
            cred = credentials.Certificate("firebase_key.json")
            firebase_admin.initialize_app(cred)
        except FileNotFoundError:
            # Se nenhum dos dois funcionar, mostra o erro e para o app
            st.error("Erro fatal: Não foi possível encontrar as credenciais do Firebase.")
            st.info("Para rodar localmente, coloque seu arquivo 'firebase_key.json' na mesma pasta do app.py.")
            st.info("Para deploy, adicione as credenciais no segredo [FIREBASE_SERVICE_ACCOUNT_KEY] do Streamlit Cloud.")
            st.stop()
    
    return firestore.client()


# --- Funções de Autenticação ---
def hash_password(password):
    """Criptografa a senha."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(password, hashed):
    """Verifica se a senha corresponde à versão criptografada."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

# --- Funções do Banco de Dados ---
def get_user_data(db, username):
    """Busca os dados do usuário no Firestore."""
    user_ref = db.collection('users').document(username)
    return user_ref.get()

def create_user(db, username, hashed_password):
    """Cria um novo usuário no Firestore."""
    db.collection('users').document(username).set({
        'password': hashed_password
    })

def get_or_create_daily_doc(db, username):
    """Pega ou cria o documento do dia para o usuário."""
    today = datetime.now().strftime("%Y-%m-%d")
    doc_ref = db.collection('users').document(username).collection('daily_data').document(today)
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.set({
            'mood': '',
            'habits': {},
            'todos': []
        })
        return doc_ref.get()
    return doc

# --- Interface do Streamlit ---

# Inicializa o estado da sessão
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# Tenta inicializar o Firebase
db = init_firebase()

# Tela de Login / Cadastro
def login_screen(db):
    st.header("Login / Cadastro")
    
    choice = st.selectbox("Escolha uma opção:", ["Login", "Cadastrar"])
    
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type='password')
    
    if choice == "Login":
        if st.button("Entrar"):
            if not username or not password:
                st.warning("Por favor, preencha todos os campos.")
                return

            user_doc = get_user_data(db, username)
            if user_doc.exists:
                user_data = user_doc.to_dict()
                if check_password(password, user_data.get('password')):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("Senha incorreta.")
            else:
                st.error("Usuário não encontrado.")

    elif choice == "Cadastrar":
        if st.button("Criar Conta"):
            if not username or not password:
                st.warning("Por favor, preencha todos os campos.")
                return

            user_doc = get_user_data(db, username)
            if user_doc.exists:
                st.error("Este nome de usuário já existe.")
            else:
                hashed = hash_password(password)
                create_user(db, username, hashed)
                st.success("Conta criada com sucesso! Agora você pode fazer o login.")


# Tela Principal do App
def main_app(db):
    st.title(f"Diário de Bordo de {st.session_state.username}")

    if st.button("Sair"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()
    
    # Pega os dados do dia
    daily_doc_snapshot = get_or_create_daily_doc(db, st.session_state.username)
    daily_data = daily_doc_snapshot.to_dict()
    doc_ref = daily_doc_snapshot.reference
    
    # --- Seção de Humor ---
    st.header("🙂 Como você está se sentindo hoje?")
    moods = ["", "Excelente", "Bem", "Normal", "Mal", "Terrível"]
    current_mood_index = moods.index(daily_data.get('mood', '')) if daily_data.get('mood') in moods else 0
    
    mood = st.selectbox("Seu humor:", moods, index=current_mood_index)
    if mood != daily_data.get('mood'):
        doc_ref.update({'mood': mood})
        st.success("Humor atualizado!")
        st.rerun()
        
    # --- Seção de Hábitos ---
    st.header("💪 Hábitos Diários")
    
    habits_list = ["Ler", "Meditar", "Exercício", "Beber 2L de água"] 
    habits_data = daily_data.get('habits', {})

    cols = st.columns(len(habits_list))
    for i, habit in enumerate(habits_list):
        with cols[i]:
            is_done = st.checkbox(habit, value=habits_data.get(habit, False), key=f"habit_{habit}")
            if is_done != habits_data.get(habit, False):
                habits_data[habit] = is_done
                doc_ref.update({'habits': habits_data})
                st.rerun()

    # --- Seção de To-Do ---
    st.header("📝 Tarefas do Dia (To-Do)")
    todos = daily_data.get('todos', [])
    
    c1, c2 = st.columns([3,1])
    with c1:
        new_todo = st.text_input("Nova tarefa:", key="new_todo_input")
    with c2:
        st.write("") # Espaçamento
        st.write("") # Espaçamento
        if st.button("Adicionar Tarefa"):
            if new_todo:
                todos.append({"task": new_todo, "done": False})
                doc_ref.update({'todos': todos})
                st.rerun()

    for i, todo in enumerate(todos):
        col1, col2 = st.columns([0.1, 0.9])
        with col1:
            done = st.checkbox("", value=todo['done'], key=f"todo_{i}")
        with col2:
            task_text = f"~~{todo['task']}~~" if todo['done'] else todo['task']
            st.write(task_text)
            
        if done != todo['done']:
            todos[i]['done'] = done
            doc_ref.update({'todos': todos})
            st.rerun()
            
# --- Lógica Principal ---
if not st.session_state.logged_in:
    login_screen(db)
else:
    main_app(db)

