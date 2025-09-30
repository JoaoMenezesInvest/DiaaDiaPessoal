import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json
from google.oauth2 import service_account
import bcrypt
from datetime import datetime, timedelta
import os
import pandas as pd
import plotly.express as px

# --- Configuração da Página ---
st.set_page_config(
    layout="wide",
    page_title="Meu Diário Pessoal",
    page_icon="📓"
)

# --- Conexão com Firebase (sem alterações) ---
def init_firebase():
    """Inicializa a conexão com o Firebase de forma segura."""
    if firebase_admin._apps:
        return firestore.client()
    try:
        key_dict = json.loads(st.secrets["FIREBASE_SERVICE_ACCOUNT_KEY"])
        project_id = key_dict.get('project_id')
        if not project_id:
            st.error("ERRO CRÍTICO: 'project_id' não encontrado nas credenciais.")
            st.stop()
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        creds = service_account.Credentials.from_service_account_info(key_dict)
        firebase_admin.initialize_app(creds)
    except (KeyError, json.JSONDecodeError):
        st.error("Erro fatal: Credenciais do Firebase não encontradas ou inválidas nos Segredos do Streamlit.")
        st.stop()
    return firestore.client()

# --- Funções de Autenticação (sem alterações) ---
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

# --- Funções de Lógica de Hábitos (sem alterações) ---
def calculate_streaks(habit_logs, habit_name):
    """Calcula a sequência atual e a maior sequência para um hábito."""
    if not habit_logs:
        return 0, 0

    sorted_dates = sorted(habit_logs.keys(), reverse=True)
    
    # Cálculo da Maior Sequência
    longest_streak = 0
    current_longest_streak = 0
    last_date = None

    all_sorted_dates = sorted(habit_logs.keys())
    for date_str in all_sorted_dates:
        if habit_logs[date_str].get(habit_name):
            current_date = datetime.strptime(date_str, "%Y-%m-%d")
            if last_date and (current_date - last_date).days == 1:
                current_longest_streak += 1
            else:
                current_longest_streak = 1
            last_date = current_date
            if current_longest_streak > longest_streak:
                longest_streak = current_longest_streak
        else:
            current_longest_streak = 0
            last_date = None

    # Cálculo da Sequência Atual
    current_streak = 0
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    # Verifica hoje
    if habit_logs.get(today.strftime("%Y-%m-%d"), {}).get(habit_name):
        current_streak = 1
        check_date = yesterday
        while True:
            if habit_logs.get(check_date.strftime("%Y-%m-%d"), {}).get(habit_name):
                current_streak += 1
                check_date -= timedelta(days=1)
            else:
                break
    # Verifica ontem se hoje não foi feito
    elif habit_logs.get(yesterday.strftime("%Y-%m-%d"), {}).get(habit_name):
        current_streak = 1
        check_date = yesterday - timedelta(days=1)
        while True:
            if habit_logs.get(check_date.strftime("%Y-%m-%d"), {}).get(habit_name):
                current_streak += 1
                check_date -= timedelta(days=1)
            else:
                break

    return current_streak, longest_streak

# --- Funções de Interface das Abas (com melhorias) ---

def render_habits_and_tasks(db, username):
    st.header("💪 Hábitos e Tarefas")

    # --- HÁBITOS ---
    st.subheader("Monitoramento de Hábitos")
    
    # Gerenciamento de Hábitos
    habits_ref = db.collection('users').document(username).collection('habits_config')
    habits_docs = habits_ref.stream()
    habits_list = [doc.id for doc in habits_docs]

    with st.expander("Gerenciar Meus Hábitos"):
        new_habit = st.text_input("Adicionar um novo hábito:")
        if st.button("Adicionar Hábito"):
            if new_habit and new_habit not in habits_list:
                habits_ref.document(new_habit).set({'created_at': datetime.now()})
                st.success(f"Hábito '{new_habit}' adicionado!")
                st.rerun()
        
        if habits_list:
            habit_to_delete = st.selectbox("Remover um hábito:", [""] + habits_list)
            if st.button("Remover Hábito Selecionado", type="primary"):
                if habit_to_delete:
                    habits_ref.document(habit_to_delete).delete()
                    st.warning(f"Hábito '{habit_to_delete}' removido.")
                    st.rerun()

    if not habits_list:
        st.info("Você ainda não adicionou nenhum hábito. Adicione um acima para começar.")
        return

    # Log de Hábitos do Dia
    st.markdown("#### Registro de Hoje")
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_log_ref = db.collection('users').document(username).collection('habits_log').document(today_str)
    today_log_doc = today_log_ref.get()
    today_log_data = today_log_doc.to_dict() if today_log_doc.exists else {}

    cols = st.columns(len(habits_list))
    for i, habit in enumerate(habits_list):
        with cols[i]:
            is_done = st.checkbox(habit, value=today_log_data.get(habit, False), key=f"habit_{habit}")
            if is_done != today_log_data.get(habit, False):
                today_log_ref.set({habit: is_done}, merge=True)
                st.rerun()

    # Estatísticas e Histórico dos Hábitos
    st.markdown("#### Análise e Histórico")
    selected_habit = st.selectbox("Selecione um hábito para ver os detalhes:", habits_list)

    if selected_habit:
        all_logs_ref = db.collection('users').document(username).collection('habits_log').stream()
        all_logs = {doc.id: doc.to_dict() for doc in all_logs_ref}
        
        current_streak, longest_streak = calculate_streaks(all_logs, selected_habit)
        
        c1, c2 = st.columns(2)
        c1.metric("🔥 Sequência Atual", f"{current_streak} dias")
        c2.metric("🏆 Maior Sequência", f"{longest_streak} dias")

        with st.expander("Ver histórico de conclusão"):
            completed_dates = []
            for date, data in sorted(all_logs.items(), reverse=True):
                if data.get(selected_habit):
                    completed_dates.append(date)
            st.table(completed_dates)

    st.divider()

    # --- TAREFAS (TO-DO) ---
    st.subheader("📝 Lista de Tarefas (Kanban)")
    tasks_ref = db.collection('users').document(username).collection('tasks')
    
    tags = ["A Fazer", "Em Progresso", "Concluído"]
    
    # Adicionar nova tarefa
    with st.form("new_task_form", clear_on_submit=True):
        c1, c2 = st.columns([3,1])
        new_task_text = c1.text_input("Nova Tarefa:")
        new_task_tag = c2.selectbox("Grupo:", tags)
        submitted = st.form_submit_button("Adicionar Tarefa")
        if submitted and new_task_text:
            tasks_ref.add({
                'task': new_task_text,
                'tag': new_task_tag,
                'created_at': datetime.now()
            })
            st.rerun()
            
    # Visualização Kanban
    cols = st.columns(len(tags))
    all_tasks = tasks_ref.stream()
    tasks_by_tag = {tag: [] for tag in tags}
    for task in all_tasks:
        task_data = task.to_dict()
        task_data['id'] = task.id
        if task_data['tag'] in tasks_by_tag:
            tasks_by_tag[task_data['tag']].append(task_data)
            
    for i, tag in enumerate(tags):
        with cols[i]:
            st.markdown(f"**{tag}**")
            for task in tasks_by_tag[tag]:
                task_id = task['id']
                task_text = task['task']
                with st.container(border=True):
                    st.write(task_text)
                    new_tag = st.selectbox("Mover para:", tags, index=tags.index(tag), key=f"tag_{task_id}", label_visibility="collapsed")
                    if new_tag != tag:
                        tasks_ref.document(task_id).update({'tag': new_tag})
                        st.rerun()


def render_mood(db, username):
    st.header("🙂 Monitoramento de Humor")

    today_str = datetime.now().strftime("%Y-%m-%d")
    mood_log_ref = db.collection('users').document(username).collection('mood_log').document(today_str)
    mood_log_doc = mood_log_ref.get()
    mood_log_data = mood_log_doc.to_dict() if mood_log_doc.exists else {}

    # Registro do Dia
    st.subheader("Como você está se sentindo hoje?")
    moods = ["", "Excelente", "Bem", "Normal", "Mal", "Terrível"]
    current_mood = mood_log_data.get('mood', '')
    current_mood_index = moods.index(current_mood) if current_mood in moods else 0
    
    selected_mood = st.selectbox("Seu humor:", moods, index=current_mood_index)
    
    journal_entry = st.text_area("Diário de hoje:", value=mood_log_data.get('journal', ''), height=200)

    if st.button("Salvar Registro de Hoje"):
        mood_log_ref.set({
            'mood': selected_mood,
            'journal': journal_entry,
            'timestamp': datetime.now()
        }, merge=True)
        st.success("Registro salvo com sucesso!")
        st.rerun()

    st.divider()

    # Histórico de Humor com Gráficos
    st.subheader("🗓️ Histórico de Humor e Diário")
    all_moods_ref = db.collection('users').document(username).collection('mood_log').order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    
    all_moods_data = []
    for mood_doc in all_moods_ref:
        data = mood_doc.to_dict()
        data['date'] = mood_doc.id
        all_moods_data.append(data)

    if all_moods_data:
        df = pd.DataFrame(all_moods_data)
        
        # Gráfico de Pizza
        mood_counts = df['mood'].value_counts()
        fig_pie = px.pie(mood_counts, values=mood_counts.values, names=mood_counts.index, title="Distribuição de Humor")
        st.plotly_chart(fig_pie, use_container_width=True)

    for data in all_moods_data:
        with st.expander(f"**{data['date']}** - Humor: **{data.get('mood', 'N/A')}**"):
            st.write(data.get('journal', '*Nenhum diário escrito.*'))

def render_future_upgrades():
    st.header("🚀 Futuros Upgrades")
    st.info("Esta área é um espaço reservado para futuras funcionalidades incríveis!")
    st.markdown("""
    Algumas ideias para o futuro:
    - Gráficos de análise de hábitos.
    - Metas de longo prazo.
    - Monitoramento de finanças.
    - Integração com calendários.
    """)
    with st.form("suggestion_form", clear_on_submit=True):
        st.write("Tem uma ideia para uma nova funcionalidade? Deixe sua sugestão!")
        suggestion = st.text_area("Sua sugestão:")
        submitted = st.form_submit_button("Enviar Sugestão")
        if submitted and suggestion:
            # Aqui você pode adicionar a lógica para salvar a sugestão em um banco de dados
            st.success("Obrigado pela sua sugestão!")

# --- Lógica Principal e Telas ---

def main_app(db, username):
    st.sidebar.title(f"Olá, {username}!")
    if st.sidebar.button("Sair"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()
    
    st.title("📓 Meu Diário Pessoal de Acompanhamento")
    
    tab1, tab2, tab3 = st.tabs(["Hábitos e Tarefas", "Meu Humor", "Futuros Upgrades"])

    with tab1:
        render_habits_and_tasks(db, username)
    with tab2:
        render_mood(db, username)
    with tab3:
        render_future_upgrades()

def login_screen(db):
    st.title("Bem-vindo ao seu Diário Pessoal")
    choice = st.selectbox("Escolha uma opção:", ["Login", "Cadastrar"])
    
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type='password')
        submitted = st.form_submit_button(choice)

        if submitted:
            user_doc = db.collection('users').document(username).get()
            if choice == "Login":
                if user_doc.exists and check_password(password, user_doc.to_dict().get('password')):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
            elif choice == "Cadastrar":
                if user_doc.exists:
                    st.error("Este nome de usuário já existe.")
                else:
                    hashed_pass = hash_password(password)
                    db.collection('users').document(username).set({'password': hashed_pass})
                    st.success("Conta criada! Agora você pode fazer o login.")


# --- Execução do App ---

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

db = init_firebase()

if st.session_state.logged_in:
    main_app(db, st.session_state.username)
else:
    login_screen(db)
