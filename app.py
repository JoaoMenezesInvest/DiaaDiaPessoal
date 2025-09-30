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
import plotly.graph_objects as go

# --- CONFIGURAÇÃO DA PÁGINA ---
# Configurações iniciais para uma aparência de tela cheia e um ícone personalizado.
st.set_page_config(
    layout="wide",
    page_title="Meu Diário Pessoal",
    page_icon="✨"
)

# --- CSS CUSTOMIZADO PARA UMA UI/UX PREMIUM ---
# Esta seção injeta um CSS complexo para transformar completamente a aparência do Streamlit.
def load_custom_css():
    st.markdown("""
        <style>
            /* --- FONTES E TEMA GERAL --- */
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
            
            html, body, [class*="st-"] {
                font-family: 'Inter', sans-serif;
            }

            .stApp {
                background-color: #121212; /* Fundo escuro profundo */
                color: #E0E0E0;
            }

            h1, h2, h3, h4, h5, h6 {
                color: #FFFFFF !important;
                font-weight: 700;
            }

            /* --- SIDEBAR --- */
            [data-testid="stSidebar"] {
                background-color: #1E1E1E;
                border-right: 1px solid #2A2A2A;
            }

            /* --- ABAS DE NAVEGAÇÃO --- */
            .stTabs [data-baseweb="tab-list"] {
                gap: 24px;
                border-bottom: 1px solid #2A2A2A;
            }
            .stTabs [data-baseweb="tab"] {
                padding: 12px 16px;
                background-color: transparent;
                border: none;
                color: #A0A0A0;
                font-weight: 500;
                transition: all 0.2s ease-in-out;
            }
            .stTabs [data-baseweb="tab"]:hover {
                color: #FFFFFF;
                background-color: #2A2A2A;
            }
            .stTabs [aria-selected="true"] {
                color: #FFFFFF;
                border-bottom: 3px solid #00A86B; /* Verde como cor de destaque */
            }

            /* --- CARDS E CONTAINERS --- */
            .st-emotion-cache-1r6slb0, [data-testid="stForm"] {
                background-color: #1E1E1E;
                border: 1px solid #2A2A2A;
                border-radius: 12px;
                padding: 24px;
                transition: box-shadow 0.3s ease, transform 0.2s ease;
            }
            .st-emotion-cache-1r6slb0:hover {
                box-shadow: 0 8px 30px rgba(0, 168, 107, 0.1);
                transform: translateY(-3px);
            }
            
            /* --- BOTÕES --- */
            .stButton>button {
                border-radius: 8px;
                border: 1px solid #00A86B;
                background-color: transparent;
                color: #00A86B;
                font-weight: 600;
                padding: 10px 16px;
                transition: all 0.2s ease;
            }
            .stButton>button:hover {
                background-color: #00A86B;
                color: #FFFFFF;
                border-color: #00A86B;
            }
            .stButton>button:focus {
                box-shadow: 0 0 0 3px rgba(0, 168, 107, 0.5) !important;
            }
            .stButton>button[kind="primary"] { /* Botão de Ação Destrutiva (Remover) */
                border-color: #C62828;
                color: #C62828;
            }
             .stButton>button[kind="primary"]:hover {
                background-color: #C62828;
                color: white;
            }

            /* --- MÉTRICAS --- */
            [data-testid="stMetric"] {
                background-color: #1E1E1E;
                border: 1px solid #2A2A2A;
                border-radius: 12px;
                padding: 20px;
            }

            /* --- INPUTS, SELECTBOX, TEXTAREA --- */
            [data-testid="stTextInput"] input, 
            [data-testid="stSelectbox"] div[data-baseweb="select"],
            [data-testid="stTextArea"] textarea {
                background-color: #2A2A2A;
                border: 1px solid #444;
                color: #E0E0E0;
                border-radius: 8px;
            }

            /* --- POPOVER --- */
            [data-testid="stPopover"] {
                background-color: #2A2A2A;
                border-radius: 8px;
            }
        </style>
    """, unsafe_allow_html=True)

load_custom_css()


# --- CONEXÃO COM FIREBASE (CACHEADO) ---
@st.cache_resource
def init_firebase():
    """Inicializa a conexão com o Firebase de forma segura usando cache."""
    try:
        key_dict = json.loads(st.secrets["FIREBASE_SERVICE_ACCOUNT_KEY"])
        creds = service_account.Credentials.from_service_account_info(key_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(creds)
    except (KeyError, json.JSONDecodeError) as e:
        st.error("Erro fatal: Credenciais do Firebase não configuradas nos Segredos do Streamlit.")
        st.exception(e)
        st.stop()
    return firestore.client()

# --- FUNÇÕES DE AUTENTICAÇÃO ---
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

# --- LÓGICA DE DADOS (COM CACHE) ---
@st.cache_data(ttl=300)
def get_all_logs(_db, username):
    logs_ref = _db.collection('users').document(username).collection('habits_log').stream()
    return {doc.id: doc.to_dict() for doc in logs_ref}

@st.cache_data(ttl=300)
def get_mood_logs(_db, username):
    moods_ref = _db.collection('users').document(username).collection('mood_log').order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    all_moods_data = [{'date': doc.id, **doc.to_dict()} for doc in moods_ref]
    return all_moods_data

def calculate_streaks(habit_logs, habit_name):
    # (Lógica mantida, pois já é eficiente)
    if not habit_logs: return 0, 0
    dates_completed = {datetime.strptime(date, "%Y-%m-%d").date() for date, data in habit_logs.items() if data.get(habit_name)}
    if not dates_completed: return 0, 0
    sorted_dates = sorted(list(dates_completed))
    longest_streak = 0
    if sorted_dates:
        current_longest_streak = 1
        longest_streak = 1
        for i in range(1, len(sorted_dates)):
            if (sorted_dates[i] - sorted_dates[i-1]).days == 1:
                current_longest_streak += 1
            else:
                current_longest_streak = 1
            longest_streak = max(longest_streak, current_longest_streak)
    current_streak = 0
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    check_date = today
    if today not in dates_completed:
        if yesterday in dates_completed:
            check_date = yesterday
        else:
            return 0, longest_streak
    while check_date in dates_completed:
        current_streak += 1
        check_date -= timedelta(days=1)
    return current_streak, longest_streak

# --- COMPONENTES DE UI (ABAS DA APLICAÇÃO) ---

def render_habits_and_tasks(db, username):
    st.header("🎯 Hábitos e Tarefas")
    st.write("Construa sua disciplina e organize suas metas com ferramentas visuais.")
    st.divider()

    st.subheader("💪 Monitoramento de Hábitos")
    
    habits_ref = db.collection('users').document(username).collection('habits_config')
    habits_list = [doc.id for doc in habits_ref.stream()]

    with st.expander("⚙️ Gerenciar Meus Hábitos"):
        with st.form("new_habit_form", clear_on_submit=True):
            new_habit = st.text_input("Adicionar novo hábito:")
            if st.form_submit_button("Adicionar Hábito"):
                if new_habit and new_habit not in habits_list:
                    habits_ref.document(new_habit).set({'created_at': firestore.SERVER_TIMESTAMP})
                    st.success(f"Hábito '{new_habit}' adicionado!")
                    st.cache_data.clear()
                    st.rerun()
        
        if habits_list:
            habit_to_delete = st.selectbox("Remover um hábito:", [""] + habits_list)
            if st.button("Remover Hábito", type="primary"):
                if habit_to_delete:
                    habits_ref.document(habit_to_delete).delete()
                    st.warning(f"Hábito '{habit_to_delete}' removido.")
                    st.cache_data.clear()
                    st.rerun()

    if not habits_list:
        st.info("Adicione seu primeiro hábito em 'Gerenciar Meus Hábitos' para começar.")
        return

    st.markdown("##### **Registro de Hoje**")
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_log_ref = db.collection('users').document(username).collection('habits_log').document(today_str)
    today_log_data = today_log_ref.get().to_dict() or {}

    cols = st.columns(len(habits_list) if habits_list else 1)
    for i, habit in enumerate(habits_list):
        with cols[i]:
            is_done = st.checkbox(habit, value=today_log_data.get(habit, False), key=f"habit_{habit}")
            if is_done != today_log_data.get(habit, False):
                today_log_ref.set({habit: is_done}, merge=True)
                st.cache_data.clear()
                st.rerun()

    st.markdown("##### **Análise e Histórico**")
    selected_habit = st.selectbox("Selecione um hábito para analisar:", habits_list)

    if selected_habit:
        all_logs = get_all_logs(db, username)
        current_streak, longest_streak = calculate_streaks(all_logs, selected_habit)
        completed_dates = [date for date, data in all_logs.items() if data.get(selected_habit)]
        
        total_days_tracked = 0
        if completed_dates:
             first_day = min([datetime.strptime(d, "%Y-%m-%d") for d in completed_dates])
             total_days_tracked = (datetime.now() - first_day).days + 1
        
        completion_rate = (len(completed_dates) / total_days_tracked) * 100 if total_days_tracked > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("🔥 Sequência Atual", f"{current_streak} dias")
        c2.metric("🏆 Maior Sequência", f"{longest_streak} dias")
        c3.metric("📈 Taxa de Conclusão", f"{completion_rate:.1f}%")

        if completed_dates:
            df = pd.DataFrame({'date': pd.to_datetime(completed_dates), 'completed': 1}).set_index('date')
            all_days = pd.date_range(start=df.index.min() - timedelta(days=1), end=datetime.now(), freq='D')
            calendar_data = df.reindex(all_days, fill_value=0)
            
            fig = px.imshow([calendar_data['completed'].values],
                            labels=dict(x="Dia", y="Hábito", color="Completado"),
                            color_continuous_scale='Greens',
                            title=f'Linha do Tempo de "{selected_habit}"')
            fig.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)


    st.divider()

    st.subheader("📝 Quadro Kanban de Tarefas")
    tasks_ref = db.collection('users').document(username).collection('tasks')
    tags = ["📌 A Fazer", "⚙️ Em Progresso", "✅ Concluído"]
    
    with st.form("new_task_form", clear_on_submit=True):
        c1, c2 = st.columns([3,1])
        new_task_text = c1.text_input("Nova Tarefa:", label_visibility="collapsed", placeholder="Ex: Estudar Machine Learning por 1 hora...")
        new_task_tag = c2.selectbox("Status:", tags, label_visibility="collapsed")
        if st.form_submit_button("＋ Adicionar Tarefa"):
            if new_task_text:
                tasks_ref.add({'task': new_task_text, 'tag': new_task_tag, 'created_at': firestore.SERVER_TIMESTAMP})
                st.rerun()
            
    cols = st.columns(len(tags))
    tasks_by_tag = {tag: [task for task in tasks_ref.where('tag', '==', tag).order_by("created_at").stream()] for tag in tags}
            
    for i, tag in enumerate(tags):
        with cols[i]:
            st.markdown(f"##### {tag}")
            for task in tasks_by_tag[tag]:
                task_data = task.to_dict()
                with st.container(border=True):
                    c1, c2 = st.columns([0.85, 0.15])
                    c1.write(task_data['task'])
                    with c2.popover("⋮"):
                        new_tag = st.selectbox("Mover:", tags, index=i, key=f"tag_{task.id}", label_visibility="collapsed")
                        if st.button("Remover", key=f"del_{task.id}", use_container_width=True, type="primary"):
                            tasks_ref.document(task.id).delete()
                            st.rerun()
                    if new_tag != tag:
                        tasks_ref.document(task.id).update({'tag': new_tag})
                        st.rerun()

def render_mood(db, username):
    st.header("😊 Análise de Humor")
    st.write("Entenda seus padrões emocionais e reflita sobre seu dia.")
    st.divider()
    
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("✍️ Registro de Hoje")
        today_str = datetime.now().strftime("%Y-%m-%d")
        mood_log_ref = db.collection('users').document(username).collection('mood_log').document(today_str)
        mood_log_data = mood_log_ref.get().to_dict() or {}
        mood_map = {"Excelente": "😄", "Bem": "🙂", "Normal": "😐", "Mal": "😕", "Terrível": "😢"}
        mood_options = list(mood_map.keys())
        current_mood = mood_log_data.get('mood', '')
        selected_mood = st.radio("Como você se sente?", options=mood_options, index=mood_options.index(current_mood) if current_mood else 0, format_func=lambda x: f"{mood_map.get(x, '')} {x}")
        journal_entry = st.text_area("Diário:", value=mood_log_data.get('journal', ''), height=200, placeholder="O que está em sua mente?")
        if st.button("Salvar Registro", type="primary", use_container_width=True):
            mood_log_ref.set({'mood': selected_mood, 'journal': journal_entry, 'timestamp': firestore.SERVER_TIMESTAMP}, merge=True)
            st.success("Registro salvo!")
            st.cache_data.clear()
            st.rerun()

    all_moods_data = get_mood_logs(db, username)
    with col2:
        st.subheader("📊 Gráficos e Insights")
        if all_moods_data:
            df = pd.DataFrame(all_moods_data)
            df['date'] = pd.to_datetime(df['date'])
            
            # NOVO: Filtro interativo para os gráficos
            date_filter = st.selectbox("Analisar período:", ["Últimos 30 dias", "Últimos 90 dias", "Todo o período"])
            today = pd.to_datetime(datetime.now().date())
            if date_filter == "Últimos 30 dias":
                df = df[df['date'] > (today - pd.Timedelta(days=30))]
            elif date_filter == "Últimos 90 dias":
                df = df[df['date'] > (today - pd.Timedelta(days=90))]

            if not df.empty:
                c1, c2 = st.columns(2)
                most_frequent_mood = df['mood'].mode()[0]
                c1.metric("Humor Frequente", f"{mood_map.get(most_frequent_mood, '❓')} {most_frequent_mood}")
                
                mood_counts = df['mood'].value_counts()
                fig_pie = px.pie(mood_counts, values=mood_counts.values, names=mood_counts.index, title="Distribuição de Humor", hole=.4)
                fig_pie.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False)
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                 st.info("Nenhum registro no período selecionado.")
        else:
            st.info("Faça seu primeiro registro de humor para ver as análises.")

    st.divider()
    st.subheader("🗓️ Histórico do Diário")
    if all_moods_data:
        for data in all_moods_data:
            with st.expander(f"**{data['date']}** - Humor: {mood_map.get(data.get('mood'), '❓')} **{data.get('mood', 'N/A')}**"):
                st.write(f"*{data.get('journal', 'Nenhum diário escrito.')}*")
    else:
        st.write("Seu histórico de diário aparecerá aqui.")

def render_future_upgrades(db):
    st.header("🚀 Futuros Upgrades")
    st.info("Sua opinião é fundamental! Ajude a moldar o futuro do app.")
    with st.form("suggestion_form", clear_on_submit=True):
        suggestion = st.text_area("Sua ideia:", placeholder="Gostaria de uma funcionalidade para...")
        if st.form_submit_button("Enviar Sugestão", use_container_width=True):
            if suggestion:
                db.collection('suggestions').add({'suggestion': suggestion, 'user': st.session_state.username,'timestamp': firestore.SERVER_TIMESTAMP})
                st.success("Obrigado pela sua sugestão!")
                st.balloons()

# --- TELAS PRINCIPAIS ---

def main_app(db, username):
    st.sidebar.title(f"Olá, {username}! ✨")
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair da Conta", use_container_width=True, type="primary"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.cache_data.clear()
        st.rerun()
    
    st.title("📓 Meu Diário Pessoal")
    st.caption(f"Bem-vindo ao seu centro de produtividade e autoconhecimento.  |  Data: {datetime.now().strftime('%d/%m/%Y')}")
    
    tab1, tab2, tab3 = st.tabs(["**🎯 Hábitos e Tarefas**", "**😊 Análise de Humor**", "**🚀 Futuros Upgrades**"])

    with tab1: render_habits_and_tasks(db, username)
    with tab2: render_mood(db, username)
    with tab3: render_future_upgrades(db)

def login_screen(db):
    st.title("✨ Bem-vindo ao seu Diário Pessoal")
    st.write("Acesse ou crie sua conta para começar a transformar sua rotina.")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        choice = st.radio("Escolha:", ["Login", "Cadastrar"], horizontal=True, label_visibility="collapsed")
        with st.form("login_form"):
            username = st.text_input("Usuário", placeholder="Seu nome de usuário")
            password = st.text_input("Senha", type='password', placeholder="Sua senha")
            
            button_label = "Entrar" if choice == "Login" else "Criar Conta"
            if st.form_submit_button(button_label, type="primary", use_container_width=True):
                if not username or not password:
                    st.error("Por favor, preencha todos os campos.")
                elif choice == "Login":
                    user_doc = db.collection('users').document(username).get()
                    if user_doc.exists and check_password(password, user_doc.to_dict().get('password')):
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.rerun()
                    else:
                        st.error("Usuário ou senha inválidos.")
                elif choice == "Cadastrar":
                    if db.collection('users').document(username).get().exists:
                        st.error("Este nome de usuário já existe.")
                    else:
                        db.collection('users').document(username).set({'password': hash_password(password), 'created_at': firestore.SERVER_TIMESTAMP})
                        st.success("Conta criada! Agora você pode fazer o login.")
                        st.balloons()
    with col2:
        st.write("") # Espaçamento
        st.image("https://storage.googleapis.com/gemini-prod/images/496739a8-7966-4d0f-8c08-164134887569.png", use_column_width=True)

# --- EXECUÇÃO PRINCIPAL DO APP ---
if __name__ == "__main__":
    db = init_firebase()

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if st.session_state.logged_in:
        main_app(db, st.session_state.username)
    else:
        login_screen(db)

