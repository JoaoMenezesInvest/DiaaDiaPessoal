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
st.set_page_config(
    layout="wide",
    page_title="Meu Diário Pessoal",
    page_icon="📓"
)

# --- CONEXÃO COM FIREBASE (CACHEADO) ---
@st.cache_resource
def init_firebase():
    """Inicializa a conexão com o Firebase de forma segura usando cache."""
    try:
        # Carrega as credenciais a partir dos segredos do Streamlit
        key_dict = json.loads(st.secrets["FIREBASE_SERVICE_ACCOUNT_KEY"])
        creds = service_account.Credentials.from_service_account_info(key_dict)
        # Inicializa o app Firebase apenas se não houver um app existente
        if not firebase_admin._apps:
            firebase_admin.initialize_app(creds)
    except (KeyError, json.JSONDecodeError) as e:
        st.error("Erro fatal: Credenciais do Firebase não configuradas nos Segredos do Streamlit.")
        st.exception(e)
        st.stop()
    return firestore.client()

# --- FUNÇÕES DE AUTENTICAÇÃO ---
def hash_password(password):
    """Gera o hash de uma senha."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(password, hashed):
    """Verifica se a senha corresponde ao hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

# --- LÓGICA DE DADOS (COM CACHE) ---
# O cache melhora drasticamente a performance, evitando buscas repetidas ao banco de dados.
@st.cache_data(ttl=300)
def get_all_logs(_db, username):
    """Busca todos os logs de hábitos para um usuário (cache de 5 min)."""
    logs_ref = _db.collection('users').document(username).collection('habits_log').stream()
    return {doc.id: doc.to_dict() for doc in logs_ref}

@st.cache_data(ttl=300)
def get_mood_logs(_db, username):
    """Busca todos os logs de humor para um usuário (cache de 5 min)."""
    moods_ref = _db.collection('users').document(username).collection('mood_log').order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    all_moods_data = []
    for doc in moods_ref:
        data = doc.to_dict()
        data['date'] = doc.id
        all_moods_data.append(data)
    return all_moods_data

def calculate_streaks(habit_logs, habit_name):
    """Calcula a sequência atual e a maior sequência para um hábito."""
    if not habit_logs: return 0, 0
    
    dates_completed = {datetime.strptime(date, "%Y-%m-%d").date() for date, data in habit_logs.items() if data.get(habit_name)}
    if not dates_completed: return 0, 0

    sorted_dates = sorted(list(dates_completed))
    
    # Cálculo da Maior Sequência
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

    # Cálculo da Sequência Atual
    current_streak = 0
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    # Define a data de início da checagem (hoje ou ontem)
    check_date = today
    if today not in dates_completed:
        if yesterday in dates_completed:
            check_date = yesterday
        else:
            return 0, longest_streak

    # Itera para trás para contar a sequência atual
    while check_date in dates_completed:
        current_streak += 1
        check_date -= timedelta(days=1)

    return current_streak, longest_streak


# --- COMPONENTES DE UI (ABAS DA APLICAÇÃO) ---

def render_habits_and_tasks(db, username):
    st.header("📅 Hábitos e Tarefas")
    st.write("Crie rotinas poderosas e organize seu dia com o Kanban.")
    st.divider()

    # --- SEÇÃO DE HÁBITOS ---
    st.subheader("💪 Monitoramento de Hábitos")
    
    habits_ref = db.collection('users').document(username).collection('habits_config')
    habits_list = [doc.id for doc in habits_ref.stream()]

    with st.expander("Gerenciar Meus Hábitos"):
        with st.form("new_habit_form", clear_on_submit=True):
            new_habit = st.text_input("Adicionar novo hábito:")
            if st.form_submit_button("Adicionar Hábito"):
                if new_habit and new_habit not in habits_list:
                    habits_ref.document(new_habit).set({'created_at': firestore.SERVER_TIMESTAMP})
                    st.success(f"Hábito '{new_habit}' adicionado!")
                    st.cache_data.clear() # Limpa o cache para recarregar os dados
                    st.rerun()
        
        if habits_list:
            habit_to_delete = st.selectbox("Remover um hábito:", [""] + habits_list)
            if st.button("Remover Hábito Selecionado", type="primary"):
                if habit_to_delete:
                    habits_ref.document(habit_to_delete).delete()
                    st.warning(f"Hábito '{habit_to_delete}' removido.")
                    st.cache_data.clear() # Limpa o cache
                    st.rerun()

    if not habits_list:
        st.info("Você ainda não adicionou hábitos. Adicione um acima para começar.")
        return

    st.markdown("##### **Registro de Hoje**")
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_log_ref = db.collection('users').document(username).collection('habits_log').document(today_str)
    today_log_data = today_log_ref.get().to_dict() or {}

    cols = st.columns(len(habits_list))
    for i, habit in enumerate(habits_list):
        with cols[i]:
            is_done = st.checkbox(habit, value=today_log_data.get(habit, False), key=f"habit_{habit}")
            if is_done != today_log_data.get(habit, False):
                today_log_ref.set({habit: is_done}, merge=True)
                st.cache_data.clear()
                st.rerun()

    st.markdown("##### **Análise e Histórico**")
    selected_habit = st.selectbox("Selecione um hábito para ver os detalhes:", habits_list)

    if selected_habit:
        all_logs = get_all_logs(db, username)
        current_streak, longest_streak = calculate_streaks(all_logs, selected_habit)
        
        c1, c2 = st.columns(2)
        c1.metric("🔥 Sequência Atual", f"{current_streak} dias")
        c2.metric("🏆 Maior Sequência", f"{longest_streak} dias")

        # NOVO: Calendário Heatmap para visualização profissional do histórico
        completed_dates = [date for date, data in all_logs.items() if data.get(selected_habit)]
        if completed_dates:
            df = pd.DataFrame({'date': pd.to_datetime(completed_dates)})
            df['count'] = 1
            df = df.set_index('date')
            
            start_date = datetime.now() - timedelta(days=365)
            all_days = pd.date_range(start=start_date, end=datetime.now(), freq='D')
            
            # Mapeia os dias para o formato do calendário
            calendar_data = pd.DataFrame(index=all_days)
            calendar_data['completed'] = df['count'].reindex(calendar_data.index).fillna(0)
            calendar_data['day_of_week'] = calendar_data.index.dayofweek
            calendar_data['week_of_year'] = calendar_data.index.isocalendar().week
            
            # Pivota os dados para o heatmap
            heatmap_data = calendar_data.pivot_table(index='day_of_week', columns='week_of_year', values='completed')
            
            fig = go.Figure(data=go.Heatmap(
                z=heatmap_data.values,
                x=heatmap_data.columns,
                y=['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'],
                colorscale='Greens',
                showscale=False,
                hoverinfo='none'
            ))
            fig.update_layout(
                title='Histórico de Conclusão (Último Ano)',
                height=250,
                margin=dict(t=50, b=0, l=0, r=0),
                xaxis_showticklabels=False
            )
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- SEÇÃO DE TAREFAS (KANBAN) ---
    st.subheader("📝 Lista de Tarefas (Kanban)")
    tasks_ref = db.collection('users').document(username).collection('tasks')
    
    tags = ["📌 A Fazer", "⚙️ Em Progresso", "✅ Concluído"]
    
    with st.form("new_task_form", clear_on_submit=True):
        st.write("**Adicionar Nova Tarefa**")
        c1, c2 = st.columns([3,1])
        new_task_text = c1.text_input("Tarefa:", label_visibility="collapsed", placeholder="Descreva a tarefa...")
        new_task_tag = c2.selectbox("Status:", tags, label_visibility="collapsed")
        if st.form_submit_button("＋ Adicionar Tarefa"):
            if new_task_text:
                tasks_ref.add({'task': new_task_text, 'tag': new_task_tag, 'created_at': firestore.SERVER_TIMESTAMP})
                st.rerun()
            
    cols = st.columns(len(tags))
    tasks_by_tag = {tag: [] for tag in tags}
    for task in tasks_ref.order_by("created_at").stream():
        task_data = task.to_dict()
        task_data['id'] = task.id
        if task_data.get('tag') in tasks_by_tag:
            tasks_by_tag[task_data['tag']].append(task_data)
            
    for i, tag in enumerate(tags):
        with cols[i]:
            st.markdown(f"##### {tag}")
            for task in tasks_by_tag[tag]:
                # Usando container com borda nativa do Streamlit
                with st.container(border=True):
                    task_id = task['id']
                    c1, c2 = st.columns([4, 1])
                    c1.write(task['task'])
                    # Popover para ações, deixando a UI mais limpa
                    with c2.popover("•••"):
                        new_tag = st.selectbox("Mover para:", tags, index=tags.index(tag), key=f"tag_{task_id}", label_visibility="collapsed")
                        if st.button("🗑️ Remover", key=f"del_{task_id}", use_container_width=True, type="primary"):
                            tasks_ref.document(task_id).delete()
                            st.rerun()
                    
                    if new_tag != tag:
                        tasks_ref.document(task_id).update({'tag': new_tag})
                        st.rerun()

def render_mood(db, username):
    st.header("😊 Monitoramento de Humor")
    st.write("Registre seu humor diário e anote seus pensamentos para autoconhecimento.")
    st.divider()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Registro de Hoje")
        today_str = datetime.now().strftime("%Y-%m-%d")
        mood_log_ref = db.collection('users').document(username).collection('mood_log').document(today_str)
        mood_log_data = mood_log_ref.get().to_dict() or {}

        mood_map = {"Excelente": "😄", "Bem": "🙂", "Normal": "😐", "Mal": "😕", "Terrível": "😢"}
        mood_options = list(mood_map.keys())
        current_mood = mood_log_data.get('mood', '')
        
        selected_mood = st.radio(
            "Como você se sente?", 
            options=mood_options, 
            index=mood_options.index(current_mood) if current_mood in mood_options else 0,
            format_func=lambda x: f"{mood_map.get(x, '')} {x}"
        )
        
        journal_entry = st.text_area("Diário de Hoje:", value=mood_log_data.get('journal', ''), height=200, placeholder="O que está em sua mente?")

        if st.button("Salvar Registro", type="primary", use_container_width=True):
            mood_log_ref.set({'mood': selected_mood, 'journal': journal_entry, 'timestamp': firestore.SERVER_TIMESTAMP}, merge=True)
            st.success("Registro salvo com sucesso!")
            st.cache_data.clear() # Limpa o cache para recarregar os gráficos
            st.rerun()

    all_moods_data = get_mood_logs(db, username)
    with col2:
        st.subheader("Análise de Humor")
        if all_moods_data:
            df = pd.DataFrame(all_moods_data)
            df['date'] = pd.to_datetime(df['date'])
            
            # Gráfico de Pizza para distribuição de humor
            mood_counts = df['mood'].value_counts()
            fig_pie = px.pie(mood_counts, values=mood_counts.values, names=mood_counts.index, title="Distribuição de Humor", hole=.4)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
            
            # Gráfico de Linha para tendência de humor
            df['mood_score'] = df['mood'].map({"Excelente": 5, "Bem": 4, "Normal": 3, "Mal": 2, "Terrível": 1})
            df_trend = df.sort_values('date').set_index('date')['mood_score'].rolling(window=7, min_periods=1).mean()
            fig_trend = px.line(df_trend, title='Tendência de Humor (Média Móvel de 7 Dias)')
            fig_trend.update_layout(yaxis_title="Pontuação de Humor", xaxis_title="Data")
            st.plotly_chart(fig_trend, use_container_width=True)

        else:
            st.info("Nenhum registro de humor encontrado para exibir análises.")

    st.divider()
    st.subheader("🗓️ Histórico do Diário")
    if all_moods_data:
        for data in all_moods_data:
            mood_icon = mood_map.get(data.get('mood'), '❓')
            with st.expander(f"**{data['date']}** - Humor: {mood_icon} **{data.get('mood', 'N/A')}**"):
                st.write(f"*{data.get('journal', 'Nenhum diário escrito.')}*")
    else:
        st.write("Seu histórico de diário aparecerá aqui.")

def render_future_upgrades(db):
    st.header("🚀 Futuros Upgrades")
    st.info("Sua opinião é importante para o futuro do app! Deixe sua sugestão abaixo.")
    
    with st.form("suggestion_form", clear_on_submit=True):
        suggestion = st.text_area("Sua ideia:", placeholder="Eu adoraria ver uma funcionalidade de...")
        if st.form_submit_button("Enviar Sugestão", use_container_width=True):
            if suggestion:
                # Salva a sugestão em uma coleção separada para análise
                db.collection('suggestions').add({
                    'suggestion': suggestion, 
                    'user': st.session_state.username,
                    'timestamp': firestore.SERVER_TIMESTAMP
                })
                st.success("Obrigado pela sua sugestão! Ela foi enviada.")
                st.balloons()

# --- TELAS PRINCIPAIS (LOGIN E APP) ---

def main_app(db, username):
    """Renderiza a aplicação principal após o login."""
    st.sidebar.title(f"Olá, {username}! 👋")
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair da Conta", use_container_width=True, type="primary"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.cache_data.clear()
        st.rerun()
    
    st.title("📓 Meu Diário Pessoal")
    st.caption("Sua ferramenta completa para autoconhecimento e produtividade.")
    
    tab1, tab2, tab3 = st.tabs(["**Hábitos e Tarefas**", "**Meu Humor**", "**Futuros Upgrades**"])

    with tab1: render_habits_and_tasks(db, username)
    with tab2: render_mood(db, username)
    with tab3: render_future_upgrades(db)

def login_screen(db):
    """Renderiza a tela de login e cadastro."""
    st.title("📓 Bem-vindo ao seu Diário Pessoal")
    st.write("Acesse sua conta ou crie uma nova para começar sua jornada.")
    
    choice = st.radio("Escolha uma opção:", ["Login", "Cadastrar"], horizontal=True, label_visibility="collapsed")
    
    with st.form("login_form"):
        username = st.text_input("Usuário", placeholder="Seu nome de usuário")
        password = st.text_input("Senha", type='password', placeholder="Sua senha")
        
        button_label = "Entrar" if choice == "Login" else "Criar Conta"
        if st.form_submit_button(button_label, type="primary", use_container_width=True):
            if not username or not password:
                st.error("Por favor, preencha todos os campos.")
                return

            if choice == "Login":
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
                    hashed_pass = hash_password(password)
                    db.collection('users').document(username).set({'password': hashed_pass, 'created_at': firestore.SERVER_TIMESTAMP})
                    st.success("Conta criada com sucesso! Agora você pode fazer o login.")
                    st.balloons()

# --- EXECUÇÃO PRINCIPAL DO APP ---
if __name__ == "__main__":
    db = init_firebase()

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if st.session_state.logged_in:
        main_app(db, st.session_state.username)
    else:
        login_screen(db)

