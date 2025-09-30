import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import bcrypt
from datetime import datetime
import json

# --- CONFIGURAÇÃO E INICIALIZAÇÃO DO FIREBASE ---

# Carrega as credenciais do Firebase a partir dos segredos do Streamlit
# Isso mantém sua chave de serviço segura e fora do código-fonte.
try:
    # Tenta carregar a chave a partir dos segredos do Streamlit (para produção)
    firebase_secrets_str = st.secrets["FIREBASE_SERVICE_ACCOUNT_KEY"]
    firebase_secrets = json.loads(firebase_secrets_str)
    cred = credentials.Certificate(firebase_secrets)
except (KeyError, json.JSONDecodeError):
    # Se falhar (ambiente de desenvolvimento local), tenta carregar de um arquivo local
    try:
        cred = credentials.Certificate("firebase_key.json")
    except Exception as e:
        st.error("Erro fatal: Não foi possível encontrar as credenciais do Firebase.")
        st.info(
            "Para rodar localmente, coloque seu arquivo 'firebase_key.json' na mesma pasta do app.py.")
        st.info(
            "Para deploy, adicione as credenciais no segredo [FIREBASE_SERVICE_ACCOUNT_KEY] do Streamlit Cloud.")
        st.stop()


# Inicializa o app Firebase apenas uma vez
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- FUNÇÕES DE AUTENTICAÇÃO E BANCO DE DADOS ---


def hash_password(password):
    """Criptografa a senha antes de salvar no banco."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())


def check_password(password, hashed):
    """Verifica se a senha fornecida corresponde à senha criptografada."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed)


def register_user(username, password):
    """Registra um novo usuário no Firestore."""
    users_ref = db.collection('users')
    if users_ref.document(username).get().exists:
        return False, "Nome de usuário já existe."

    hashed_password = hash_password(password)
    users_ref.document(username).set({
        'password': hashed_password
    })
    return True, "Usuário registrado com sucesso!"


def validate_login(username, password):
    """Valida as credenciais do usuário."""
    users_ref = db.collection('users')
    user_doc = users_ref.document(username).get()

    if not user_doc.exists:
        return False

    user_data = user_doc.to_dict()
    hashed_password = user_data.get('password')

    return check_password(password, hashed_password)


def get_today_data_ref(username):
    """Retorna a referência do documento para os dados de hoje do usuário."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    return db.collection('users').document(username).collection('data').document(today_str)


def load_data(username):
    """Carrega os dados de hoje para o usuário logado."""
    data_ref = get_today_data_ref(username)
    doc = data_ref.get()
    if doc.exists:
        return doc.to_dict()
    # Retorna uma estrutura padrão se não houver dados para o dia
    return {'mood': None, 'habits': {}, 'tasks': []}


def save_data(username, data):
    """Salva os dados de hoje para o usuário logado."""
    data_ref = get_today_data_ref(username)
    data_ref.set(data)

# --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---


if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'data' not in st.session_state:
    st.session_state.data = {}

# --- LÓGICA DE LOGIN E REGISTRO NA BARRA LATERAL ---


def login_form():
    st.sidebar.title("Login")
    username = st.sidebar.text_input("Usuário", key="login_user")
    password = st.sidebar.text_input(
        "Senha", type="password", key="login_pass")

    if st.sidebar.button("Entrar"):
        if validate_login(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            # Carrega os dados após o login
            st.session_state.data = load_data(username)
            st.rerun()
        else:
            st.sidebar.error("Usuário ou senha inválidos.")


def register_form():
    st.sidebar.title("Registro")
    new_username = st.sidebar.text_input("Novo Usuário", key="reg_user")
    new_password = st.sidebar.text_input(
        "Nova Senha", type="password", key="reg_pass")

    if st.sidebar.button("Registrar"):
        if new_username and new_password:
            success, message = register_user(new_username, new_password)
            if success:
                st.sidebar.success(message)
            else:
                st.sidebar.error(message)
        else:
            st.sidebar.warning("Por favor, preencha todos os campos.")


# Exibe o formulário de login ou registro se não estiver logado
if not st.session_state.logged_in:
    choice = st.sidebar.radio("Escolha uma ação", ["Login", "Registro"])
    if choice == "Login":
        login_form()
    else:
        register_form()
    st.title("Bem-vindo ao seu Diário Pessoal!")
    st.write("Faça login ou registre-se na barra lateral para continuar.")
    st.stop()  # Interrompe a execução do restante do app

# --- APLICAÇÃO PRINCIPAL (SÓ APARECE APÓS O LOGIN) ---

# Cabeçalho
st.title(f"Diário de {st.session_state.username}")
st.markdown(f"**Data:** {datetime.now().strftime('%d/%m/%Y')}")

# Botão de Logout
if st.sidebar.button("Sair"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.data = {}
    st.rerun()

# Carrega os dados na primeira vez ou após o login
if not st.session_state.data:
    st.session_state.data = load_data(st.session_state.username)

# Seção de Humor
st.header("😊 Como você está se sentindo hoje?")
mood_options = ['🤩 Incrível', '😊 Bem', '😐 Normal', '😕 Mal', '😢 Péssimo']
selected_mood = st.radio(
    "Selecione seu humor:",
    mood_options,
    index=mood_options.index(st.session_state.data.get(
        'mood')) if st.session_state.data.get('mood') in mood_options else 2,
    horizontal=True
)
if selected_mood != st.session_state.data.get('mood'):
    st.session_state.data['mood'] = selected_mood
    save_data(st.session_state.username, st.session_state.data)

st.divider()

# Seção de Hábitos
st.header("💪 Hábitos de Hoje")
col1, col2 = st.columns([3, 1])
new_habit = col1.text_input("Adicionar novo hábito",
                            placeholder="Ex: Ler 10 páginas")
if col2.button("Adicionar Hábito", use_container_width=True):
    if new_habit:
        if 'habits' not in st.session_state.data:
            st.session_state.data['habits'] = {}
        st.session_state.data['habits'][new_habit] = False
        save_data(st.session_state.username, st.session_state.data)
        st.rerun()

if 'habits' in st.session_state.data and st.session_state.data['habits']:
    for habit, completed in list(st.session_state.data['habits'].items()):
        col_habit, col_delete = st.columns([0.9, 0.1])
        is_checked = col_habit.checkbox(
            habit, value=completed, key=f"habit_{habit}")
        if is_checked != completed:
            st.session_state.data['habits'][habit] = is_checked
            save_data(st.session_state.username, st.session_state.data)

        if col_delete.button("🗑️", key=f"del_{habit}", help=f"Remover '{habit}'"):
            del st.session_state.data['habits'][habit]
            save_data(st.session_state.username, st.session_state.data)
            st.rerun()
else:
    st.write("Nenhum hábito adicionado para hoje.")

st.divider()

# Seção de Tarefas
st.header("✅ Tarefas do Dia (To-Do)")
col1_task, col2_task = st.columns([3, 1])
new_task = col1_task.text_input(
    "Adicionar nova tarefa", placeholder="Ex: Pagar a conta de luz")
if col2_task.button("Adicionar Tarefa", use_container_width=True):
    if new_task:
        if 'tasks' not in st.session_state.data:
            st.session_state.data['tasks'] = []
        st.session_state.data['tasks'].append(
            {'text': new_task, 'completed': False})
        save_data(st.session_state.username, st.session_state.data)
        st.rerun()

if 'tasks' in st.session_state.data and st.session_state.data['tasks']:
    for i, task in enumerate(st.session_state.data['tasks']):
        col_task_check, col_task_delete = st.columns([0.9, 0.1])
        task_completed = col_task_check.checkbox(
            f"~~{task['text']}~~" if task['completed'] else task['text'],
            value=task['completed'],
            key=f"task_{i}"
        )
        if task_completed != task['completed']:
            st.session_state.data['tasks'][i]['completed'] = task_completed
            save_data(st.session_state.username, st.session_state.data)

        if col_task_delete.button("🗑️", key=f"del_task_{i}", help=f"Remover '{task['text']}'"):
            st.session_state.data['tasks'].pop(i)
            save_data(st.session_state.username, st.session_state.data)
            st.rerun()
else:
    st.write("Nenhuma tarefa para hoje.")
