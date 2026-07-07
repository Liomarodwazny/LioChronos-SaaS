import streamlit as st
import pandas as pd
import math
import uuid
import json
import base64
import os
import tempfile
import random
from ortools.sat.python import cp_model
from io import BytesIO
from fpdf import FPDF

# ==========================================
# 1. CONFIGURAÇÃO VISUAL E CONEXÃO SUPABASE
# ==========================================
st.set_page_config(page_title="LioChronos - Gestão Escolar", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #F5F4F1; color: #1F2420; }
    .stButton > button { background-color: #4F7A54; color: white; border-radius: 6px; border: none; }
    .stButton > button:hover { background-color: #436A49; color: white; }
    h1, h2, h3 { color: #22281F; }
    </style>
""", unsafe_allow_html=True)

# Tenta ligar ao banco de dados Supabase usando as chaves guardadas nos Secrets
try:
    from supabase import create_client, Client
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
    banco_ligado = True
except:
    banco_ligado = False

# ==========================================
# 2. SISTEMA DE LOGIN (PORTA DE ENTRADA SaaS)
# ==========================================
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

CLIENTES_CADASTRADOS = {
    "admin": "sabereducativo2026",
    "carrossel": "carrossel123",
    "escola_teste": "teste123",
    "coruje": "coruja2026"
}

if not st.session_state['autenticado']:
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #4F7A54;'>⚙️ LioChronos</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Gestão Inteligente de Horários Escolares<br>Acesso restrito a instituições parceiras do Sabereducativo.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            usuario = st.text_input("Utilizador")
            senha = st.text_input("Palavra-passe", type="password")
            submit = st.form_submit_button("Entrar no Sistema", use_container_width=True)
            
            if submit:
                if usuario in CLIENTES_CADASTRADOS and CLIENTES_CADASTRADOS[usuario] == senha:
                    st.session_state['autenticado'] = True
                    st.session_state['cliente_atual'] = usuario
                    
                    # MAGIA DA NUVEM: Carrega os dados da escola instantaneamente após o login
                    if banco_ligado:
                        try:
                            resposta = supabase.table('clientes_dados').select("dados").eq("cliente", usuario).execute()
                            if resposta.data:
                                dados = resposta.data[0]['dados']
                                st.session_state.config = dados.get('config', {'dias': ['Seg', 'Ter', 'Qua', 'Qui', 'Sex'], 'periodos': 9, 'escola_nome': '', 'escola_logo': None})
                                st.session_state.disciplinas = dados.get('disciplinas', [])
                                st.session_state.turmas = dados.get('turmas', [])
                                st.session_state.professores = dados.get('professores', [])
                                st.session_state.grade = dados.get('grade', [])
                        except Exception as e:
                            pass # Se a escola for nova e não tiver guardado nada ainda, entra em branco
                            
                    st.rerun()
                else:
                    st.error("❌ Utilizador ou palavra-passe incorretos.")
                    
    st.stop()

# ==========================================
# 3. INICIALIZAÇÃO DA MEMÓRIA 
# ==========================================
if 'config' not in st.session_state:
    st.session_state.config = {'dias': ['Seg', 'Ter', 'Qua', 'Qui', 'Sex'], 'periodos': 9, 'escola_nome': '', 'escola_logo': None}
if 'disciplinas' not in st.session_state:
    st.session_state.disciplinas = []
if 'turmas' not in st.session_state:
    st.session_state.turmas = []
if 'professores' not in st.session_state:
    st.session_state.professores = []
if 'grade' not in st.session_state:
    st.session_state.grade = []
if 'edit_grade_id' not in st.session_state:
    st.session_state.edit_grade_id = None

def gerar_id(): return uuid.uuid4().hex[:8]
def get_nome(lista, _id): return next((item['nome'] for item in lista if item['id'] == _id), "Desconhecido")
def limpar_texto_pdf(texto): return str(texto).replace(" \n", " - ").encode('latin-1', 'replace').decode('latin-1')

# ==========================================
# 4. BARRA LATERAL (SINCRONIZAÇÃO NUVEM E JSON)
# ==========================================
with st.sidebar:
    st.header(f"👤 {st.session_state.get('cliente_atual', '').capitalize()}")
    if st.button("Sair (Logout)", use_container_width=True):
        st.session_state['autenticado'] = False
        st.rerun()
        
    st.markdown("---")
    st.header("☁️ Backup e Sincronização")
    
    dados_export = {
        'config': st.session_state.config,
        'disciplinas': st.session_state.disciplinas,
        'turmas': st.session_state.turmas,
        'professores': st.session_state.professores,
        'grade': st.session_state.grade
    }
    
    # --- BOTÃO DE GUARDAR NA NUVEM ---
    if banco_ligado:
        st.success("🟢 Conectado ao Supabase")
        if st.button("💾 Guardar na Nuvem", type="primary", use_container_width=True, help="Grava todas as turmas e professores nos servidores centrais."):
            try:
                # O Upsert com on_conflict cria a gaveta se for novo, ou atualiza se já existir
                supabase.table('clientes_dados').upsert(
                    {"cliente": st.session_state['cliente_atual'], "dados": dados_export}, 
                    on_conflict="cliente"
                ).execute()
                st.toast("✅ Trabalho guardado em segurança na nuvem!", icon="☁️")
            except Exception as e:
                st.error(f"❌ Erro de comunicação: {e}")
    else:
        st.warning("⚠️ Banco de dados offline. A trabalhar no modo local.")
        
    st.markdown("---")
    
    # --- BOTÕES DE EXPORTAR / IMPORTAR JSON ---
    st.subheader("⬇️ Exportar Backup")
    json_str = json.dumps(dados_export, indent=2)
    st.download_button(
        label="⭳ Descarregar Arquivo (.json)", 
        data=json_str, 
        file_name="LioChronos_Backup.json", 
        mime="application/json", 
        use_container_width=True
    )
    
    st.markdown("---")
    st.subheader("⬆️ Importar Backup")
    st.info("Pode carregar um ficheiro .json antigo para o sistema.")
    arquivo_importado = st.file_uploader("Carregar JSON", type=["json"])
    if arquivo_importado is not None:
        if st.button("Restaurar Dados do Ficheiro", use_container_width=True):
            try:
                dados = json.load(arquivo_importado)
                st.session_state.config = dados.get('config', st.session_state.config)
                st.session_state.disciplinas = dados.get('disciplinas', [])
                st.session_state.turmas = dados.get('turmas', [])
                st.session_state.professores = dados.get('professores', [])
                st.session_state.grade = dados.get('grade', [])
                st.success("✅ Dados restaurados! (Lembre-se de Guardar na Nuvem)")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler ficheiro: {e}")

# ==========================================
# 5. INTERFACE DE ABAS
# ==========================================
st.title("⚙️ LioChronos - Gestão Escolar")

aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs([
    "⚙️ Configuração", "📚 Disciplinas", "🏫 Turmas", "👩‍🏫 Professores", "📅 Grade Curricular", "🚀 Gerador"
])

with aba1:
    st.subheader("Configurações Base e Identidade da Escola")
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.config['escola_nome'] = st.text_input("Nome da Escola (Aparece no PDF)", value=st.session_state.config.get('escola_nome', ''))
        st.session_state.config['periodos'] = st.number_input("Horários (Aulas) por dia", min_value=1, max_value=12, value=st.session_state.config.get('periodos', 9))
    with col2:
        # MOSTRA A IMAGEM SE ELA JÁ EXISTIR NA MEMÓRIA/NUVEM
        if st.session_state.config.get('escola_logo'):
            st.write("**Logótipo Guardado:**")
            st.image(st.session_state.config['escola_logo'], width=150)
            if st.button("🗑️ Remover Logótipo"):
                st.session_state.config['escola_logo'] = None
                st.rerun()
                
        # CAIXA PARA CARREGAR UMA NOVA IMAGEM
        logo_upload = st.file_uploader("Carregar novo Logótipo (Opcional - Usado no PDF)", type=["png", "jpg", "jpeg"])
        if logo_upload:
            b64 = base64.b64encode(logo_upload.getvalue()).decode()
            st.session_state.config['escola_logo'] = f"data:image/png;base64,{b64}"
            st.success("Logótipo carregado com sucesso! Lembre-se de Guardar na Nuvem.")
            st.rerun()
        
        opcoes_dias = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']
        dias_salvos = [d for d in st.session_state.config.get('dias', []) if d in opcoes_dias]
        st.session_state.config['dias'] = st.multiselect("Dias Letivos", opcoes_dias, default=dias_salvos)

with aba2:
    st.subheader("Disciplinas")
    with st.form("form_disc"):
        col_n, col_p, col_b = st.columns([3, 1, 1])
        nome_disc = col_n.text_input("Nome da Disciplina")
        pesada = col_p.checkbox("Matéria Pesada?")
        if col_b.form_submit_button("Adicionar"):
            if nome_disc:
                st.session_state.disciplinas.append({'id': gerar_id(), 'nome': nome_disc, 'pesada': pesada})
                st.rerun()
                
    if st.session_state.disciplinas:
        for d in st.session_state.disciplinas:
            c1, c2, c3 = st.columns([4, 2, 1])
            c1.write(f"**{d['nome']}**")
            c2.write("⚖️ Pesada" if d.get('pesada', False) else "🍃 Leve")
            if c3.button("🗑️ Eliminar", key=f"del_d_{d['id']}"):
                st.session_state.disciplinas = [x for x in st.session_state.disciplinas if x['id'] != d['id']]
                st.rerun()

with aba3:
    st.subheader("Turmas")
    with st.form("form_turma"):
        col_t, col_b = st.columns([4, 1])
        nome_turma = col_t.text_input("Nome da Turma (Ex: 6º Ano A)")
        if col_b.form_submit_button("Adicionar"):
            if nome_turma:
                st.session_state.turmas.append({'id': gerar_id(), 'nome': nome_turma})
                st.rerun()
                
    if st.session_state.turmas:
        for t in st.session_state.turmas:
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.write(f"🏫 **{t['nome']}**")
            
            if c2.button("📋 Duplicar", key=f"dup_t_{t['id']}", help="Copia a turma e as suas disciplinas"):
                novo_id = gerar_id()
                st.session_state.turmas.append({'id': novo_id, 'nome': f"{t['nome']} (Cópia)"})
                
                regras_originais = [g for g in st.session_state.grade if g['turmaId'] == t['id']]
                for regra in regras_originais:
                    nova_regra = regra.copy()
                    nova_regra['id'] = gerar_id()
                    nova_regra['turmaId'] = novo_id
                    st.session_state.grade.append(nova_regra)
                st.rerun()
                
            if c3.button("🗑️ Eliminar", key=f"del_t_{t['id']}"):
                st.session_state.turmas = [x for x in st.session_state.turmas if x['id'] != t['id']]
                st.session_state.grade = [g for g in st.session_state.grade if g['turmaId'] != t['id']]
                st.rerun()

with aba4:
    st.subheader("Professores e Disponibilidade")
    with st.form("form_prof"):
        nome_prof = st.text_input("Novo Professor")
        if st.form_submit_button("Criar Professor"):
            if nome_prof:
                st.session_state.professores.append({'id': gerar_id(), 'nome': nome_prof, 'disciplinas': [], 'indisponibilidade': []})
                st.rerun()

    if st.session_state.professores:
        for prof in st.session_state.professores:
            with st.expander(f"👩‍🏫 {prof['nome']} ({len(prof.get('indisponibilidade', []))} bloqueios)"):
                opcoes_disc = {d['id']: d['nome'] for d in st.session_state.disciplinas}
                disc_validas = [d for d in prof.get('disciplinas', []) if d in opcoes_disc]
                
                selecionadas = st.multiselect("Disciplinas que leciona", options=list(opcoes_disc.keys()), format_func=lambda x: opcoes_disc[x], default=disc_validas, key=f"disc_{prof['id']}")
                prof['disciplinas'] = selecionadas
                
                dias = st.session_state.config.get('dias', [])
                periodos = st.session_state.config.get('periodos', 9)
                
                st.markdown("**Ações Rápidas (Preenchimento Automático):**")
                c1, c2, c3 = st.columns(3)
                meio = math.ceil(periodos / 2)
                
                def aplicar_turno(tipo, p_id):
                    p_atual = next(p for p in st.session_state.professores if p['id'] == p_id)
                    novo_indisp = []
                    if tipo != 'limpar':
                        for d in dias:
                            for per in range(1, periodos + 1):
                                if tipo == 'manha' and per > meio: novo_indisp.append(f"{d}-{per}")
                                if tipo == 'tarde' and per <= meio: novo_indisp.append(f"{d}-{per}")
                    p_atual['indisponibilidade'] = novo_indisp
                    
                    if f"malha_{p_id}" in st.session_state:
                        del st.session_state[f"malha_{p_id}"]

                if c1.button("☀️ Só Manhã", key=f"m_{prof['id']}"): 
                    aplicar_turno('manha', prof['id'])
                    st.rerun()
                if c2.button("🌤️ Só Tarde", key=f"t_{prof['id']}"): 
                    aplicar_turno('tarde', prof['id'])
                    st.rerun()
                if c3.button("🔄 Limpar Tudo", key=f"l_{prof['id']}"): 
                    aplicar_turno('limpar', prof['id'])
                    st.rerun()

                st.markdown("**Ajuste Fino (Marque/Desmarque manualmente):**")
                
                with st.form(f"form_malha_{prof['id']}"):
                    malha_dados = {dia: [(f"{dia}-{p}" not in prof.get('indisponibilidade', [])) for p in range(1, periodos + 1)] for dia in dias}
                    df_malha = pd.DataFrame(malha_dados, index=[f"{p}º" for p in range(1, periodos + 1)])
                    
                    malha_editada = st.data_editor(df_malha, key=f"malha_{prof['id']}", use_container_width=True)
                    
                    if st.form_submit_button("💾 Guardar Horários deste Professor"):
                        novo_indisp = []
                        for dia in dias:
                            for per in range(1, periodos + 1):
                                if not malha_editada.at[f"{per}º", dia]: 
                                    novo_indisp.append(f"{dia}-{per}")
                        prof['indisponibilidade'] = novo_indisp
                        st.success("✅ Horários guardados com sucesso!")

                st.markdown("---")
                if st.button("🗑️ Eliminar Professor", key=f"del_p_{prof['id']}"):
                    st.session_state.professores = [x for x in st.session_state.professores if x['id'] != prof['id']]
                    st.rerun()

with aba5:
    st.subheader("Grade Curricular")
    if not st.session_state.turmas or not st.session_state.disciplinas or not st.session_state.professores:
        st.warning("Registe Turmas, Disciplinas e Professores antes de montar a grade.")
    else:
        opcoes_turmas = {t['id']: t['nome'] for t in st.session_state.turmas}
        turma_selecionada = st.selectbox("Selecione a Turma", options=list(opcoes_turmas.keys()), format_func=lambda x: opcoes_turmas[x])
        
        st.write("#### Adicionar Disciplina na Turma")
        st.info("💡 A lista de professores ajusta-se automaticamente com base na disciplina escolhida.")
        
        linha1_col1, linha1_col2, linha1_col3 = st.columns(3)
        linha2_col1, linha2_col2, linha2_col3 = st.columns(3)
        
        opcoes_disc = {d['id']: d['nome'] for d in st.session_state.disciplinas}
        disc_id = linha1_col1.selectbox("Disciplina", options=list(opcoes_disc.keys()), format_func=lambda x: opcoes_disc[x])
        
        profs_validos = {p['id']: p['nome'] for p in st.session_state.professores if disc_id in p.get('disciplinas', [])}
        prof_id = linha1_col2.selectbox("Professor Titular", options=list(profs_validos.keys()), format_func=lambda x: profs_validos.get(x, "Nenhum"))
        
        opcoes_codocentes = [None] + list(profs_validos.keys())
        prof_sec_id = linha1_col3.selectbox("Co-docente (Opcional)", options=opcoes_codocentes, format_func=lambda x: profs_validos.get(x, "Nenhum (Só titular)"))
        
        aulas_sem = linha2_col1.number_input("Aulas/Semana", min_value=1, max_value=20, value=3)
        bloco = linha2_col2.selectbox("Tamanho do Bloco", [1, 2, 3], index=0)
        
        linha2_col3.write("") 
        if linha2_col3.button("➕ Adicionar à Grade", use_container_width=True):
            if not prof_id:
                st.error("Registe um professor que lecione esta disciplina primeiro!")
            elif prof_sec_id and prof_id == prof_sec_id:
                st.error("O professor titular e o co-docente não podem ser a mesma pessoa!")
            else:
                st.session_state.grade.append({
                    'id': gerar_id(), 'turmaId': turma_selecionada, 'disciplinaId': disc_id, 
                    'professorId': prof_id, 'professorIdSecundario': prof_sec_id, 
                    'aulasSemana': aulas_sem, 'blocoTamanho': bloco
                })
                st.rerun()

        st.markdown("---")
        st.markdown("#### Matriz da Turma")
        grade_turma = [g for g in st.session_state.grade if g['turmaId'] == turma_selecionada]
        
        if grade_turma:
            for item in grade_turma:
                # --- MODO DE VISUALIZAÇÃO ---
                c1, c2, c3, c4, c5, c6 = st.columns([3, 3, 2, 2, 1, 1])
                c1.write(get_nome(st.session_state.disciplinas, item['disciplinaId']))
                
                nome_prof = get_nome(st.session_state.professores, item['professorId'])
                if item.get('professorIdSecundario'): 
                    nome_prof += f" & {get_nome(st.session_state.professores, item['professorIdSecundario'])}"
                c2.write(nome_prof)
                c3.write(f"Aulas: {item['aulasSemana']}")
                c4.write(f"Bloco: {item.get('blocoTamanho', 1)}x")
                
                # --- BOTÃO EDITAR ---
                if c5.button("✏️", key=f"edit_g_{item['id']}", help="Editar esta regra"):
                    st.session_state.edit_grade_id = item['id']
                    st.rerun()
                    
                if c6.button("🗑️", key=f"del_g_{item['id']}", help="Eliminar regra"):
                    st.session_state.grade = [x for x in st.session_state.grade if x['id'] != item['id']]
                    st.rerun()
                    
                # --- MODO DE EDIÇÃO (Abre se clicar no botão) ---
                if st.session_state.get('edit_grade_id') == item['id']:
                    with st.container():
                        st.info(f"✏️ **A editar a regra de:** {get_nome(st.session_state.disciplinas, item['disciplinaId'])}")
                        with st.form(key=f"form_ed_{item['id']}"):
                            ec1, ec2, ec3 = st.columns(3)
                            
                            profs_validos = {p['id']: p['nome'] for p in st.session_state.professores if item['disciplinaId'] in p.get('disciplinas', [])}
                            
                            idx_prof = list(profs_validos.keys()).index(item['professorId']) if item['professorId'] in profs_validos else 0
                            novo_prof = ec1.selectbox("Prof. Titular", options=list(profs_validos.keys()), format_func=lambda x: profs_validos.get(x, "Nenhum"), index=idx_prof, key=f"ep_{item['id']}")

                            op_codoc = [None] + list(profs_validos.keys())
                            idx_sec = op_codoc.index(item.get('professorIdSecundario')) if item.get('professorIdSecundario') in op_codoc else 0
                            novo_sec = ec2.selectbox("Co-docente", options=op_codoc, format_func=lambda x: profs_validos.get(x, "Nenhum"), index=idx_sec, key=f"es_{item['id']}")

                            novas_aulas = ec3.number_input("Aulas/Semana", min_value=1, max_value=20, value=item['aulasSemana'], key=f"ea_{item['id']}")
                            novo_bloco = ec3.selectbox("Bloco Máximo", [1, 2, 3], index=[1, 2, 3].index(item.get('blocoTamanho', 1)), key=f"eb_{item['id']}")

                            sc1, sc2 = st.columns([1, 4])
                            if sc1.form_submit_button("💾 Guardar", type="primary"):
                                item['professorId'] = novo_prof
                                item['professorIdSecundario'] = novo_sec
                                item['aulasSemana'] = novas_aulas
                                item['blocoTamanho'] = novo_bloco
                                st.session_state.edit_grade_id = None
                                st.rerun()
                                
                            if sc2.form_submit_button("❌ Cancelar"):
                                st.session_state.edit_grade_id = None
                                st.rerun()
                        st.markdown("---")
        else:
            st.info("Nenhuma disciplina adicionada para esta turma ainda.")

# --- ABA 6: O MOTOR GERADOR E EXPORTAÇÃO ---
with aba6:
    st.subheader("Processamento e Geração")
    total_aulas = sum(g.get('aulasSemana', 0) for g in st.session_state.grade)
    st.write(f"Total de regras a calcular: **{total_aulas} aulas semanais.**")
    
    if st.button("🚀 Iniciar Motor Google OR-Tools", use_container_width=True):
        with st.spinner("A processar restrições matemáticas complexas..."):
            model = cp_model.CpModel()
            grade_vars = {}
            dias = st.session_state.config.get('dias', [])
            num_dias = len(dias)
            num_periodos = st.session_state.config.get('periodos', 9)
            grade_reqs = st.session_state.grade
            
            for d in range(num_dias):
                for p in range(num_periodos):
                    for i, req in enumerate(grade_reqs):
                        grade_vars[(d, p, i)] = model.NewBoolVar(f'v_{d}_{p}_{i}')

            for i, req in enumerate(grade_reqs):
                model.Add(sum(grade_vars[(d, p, i)] for d in range(num_dias) for p in range(num_periodos)) == req.get('aulasSemana', 0))

            for d in range(num_dias):
                for p in range(num_periodos):
                    for t_id in [t['id'] for t in st.session_state.turmas]:
                        model.AddAtMostOne(grade_vars[(d, p, i)] for i, r in enumerate(grade_reqs) if r['turmaId'] == t_id)

            for d in range(num_dias):
                for p in range(num_periodos):
                    for p_id in [p['id'] for p in st.session_state.professores]:
                        reqs_do_prof = [i for i, r in enumerate(grade_reqs) if r['professorId'] == p_id or r.get('professorIdSecundario') == p_id]
                        model.AddAtMostOne(grade_vars[(d, p, i)] for i in reqs_do_prof)

            for prof in st.session_state.professores:
                reqs_do_prof = [i for i, r in enumerate(grade_reqs) if r['professorId'] == prof['id'] or r.get('professorIdSecundario') == prof['id']]
                for indis in prof.get('indisponibilidade', []):
                    try:
                        dia_str, per_str = indis.split('-')
                        if dia_str in dias:
                            for i in reqs_do_prof:
                                model.Add(grade_vars[(dias.index(dia_str), int(per_str) - 1, i)] == 0)
                    except ValueError: pass

            for i, req in enumerate(grade_reqs):
                limite_diario = max(req.get('blocoTamanho', 1), math.ceil(req.get('aulasSemana', 0) / max(1, num_dias)))
                for d in range(num_dias):
                    model.Add(sum(grade_vars[(d, p, i)] for p in range(num_periodos)) <= limite_diario)

            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = 30.0 
            
            solver.parameters.randomize_search = True
            solver.parameters.random_seed = random.randint(1, 10000)
            
            status = solver.Solve(model)

            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                resultado = []
                for d in range(num_dias):
                    for p in range(num_periodos):
                        for i, req in enumerate(grade_reqs):
                            if solver.Value(grade_vars[(d, p, i)]) == 1:
                                prof_str = get_nome(st.session_state.professores, req['professorId'])
                                if req.get('professorIdSecundario'): prof_str += f" & {get_nome(st.session_state.professores, req['professorIdSecundario'])}"
                                resultado.append({
                                    'Turma': get_nome(st.session_state.turmas, req['turmaId']),
                                    'Dia': dias[d], 'Período': p + 1,
                                    'Disciplina': get_nome(st.session_state.disciplinas, req['disciplinaId']),
                                    'Professor': prof_str
                                })
                st.session_state.horario_final = pd.DataFrame(resultado)
                st.success("✨ Solução Encontrada e Gerada!")
            else:
                st.error("❌ Conflito Inviável! O motor não conseguiu fechar a grade. Veja o diagnóstico abaixo:")
                st.session_state.horario_final = None
                
                max_aulas_semana = num_dias * num_periodos
                erros_diag = []
                
                for t in st.session_state.turmas:
                    aulas_turma = sum(g.get('aulasSemana', 0) for g in grade_reqs if g['turmaId'] == t['id'])
                    if aulas_turma > max_aulas_semana:
                        erros_diag.append(f"🏫 **Turma {t['nome']}**: Tem {aulas_turma} aulas na grade, mas a semana só tem {max_aulas_semana} horários.")
                        
                for prof in st.session_state.professores:
                    aulas_prof = sum(g.get('aulasSemana', 0) for g in grade_reqs if g['professorId'] == prof['id'] or g.get('professorIdSecundario') == prof['id'])
                    
                    bloqueios_validos = 0
                    for ind in prof.get('indisponibilidade', []):
                        try:
                            if ind.split('-')[0] in dias:
                                bloqueios_validos += 1
                        except: pass
                            
                    horarios_livres = max_aulas_semana - bloqueios_validos
                    
                    if aulas_prof > horarios_livres:
                        erros_diag.append(f"👩‍🏫 **Prof(a). {prof['nome']}**: Precisa dar {aulas_prof} aulas na grade, mas só tem {horarios_livres} horários livres marcados na malha (possui {bloqueios_validos} bloqueios).")
                        
                if erros_diag:
                    for e in erros_diag:
                        st.warning(e)
                else:
                    st.warning("🕵️ **Conflito Cruzado Complexo:** A matemática individual fecha, mas o cruzamento dos horários bloqueados entre vários professores impede que o quadro seja montado. É um efeito dominó.")
                    
                    st.markdown("### 🔍 Raio-X dos Suspeitos (Gargalos)")
                    st.write("Estes são os professores com as agendas mais 'estranguladas'. Têm muitos bloqueios para a quantidade de aulas que precisam dar. **Tente libertar horários na malha deles:**")
                    
                    prof_stats = []
                    for prof in st.session_state.professores:
                        aulas_prof = sum(g.get('aulasSemana', 0) for g in grade_reqs if g['professorId'] == prof['id'] or g.get('professorIdSecundario') == prof['id'])
                        
                        bloqueios_validos = 0
                        for ind in prof.get('indisponibilidade', []):
                            try:
                                if ind.split('-')[0] in dias:
                                    bloqueios_validos += 1
                            except: pass
                                
                        horarios_livres = max_aulas_semana - bloqueios_validos
                        
                        if aulas_prof > 0 and horarios_livres > 0:
                            taxa = (aulas_prof / horarios_livres) * 100
                            prof_stats.append({
                                'nome': prof['nome'], 
                                'aulas': aulas_prof, 
                                'livres': horarios_livres, 
                                'bloqueios': bloqueios_validos,
                                'taxa': taxa
                            })
                    
                    prof_stats.sort(key=lambda x: (x['taxa'], x['bloqueios']), reverse=True)
                    
                    for p in prof_stats[:5]:
                        if p['taxa'] >= 80:
                            cor = "🔴"
                        elif p['taxa'] >= 60:
                            cor = "🟠"
                        else:
                            cor = "🟡"
                            
                        st.markdown(f"{cor} **Prof(a). {p['nome']}**: {p['bloqueios']} horários bloqueados. (Ocupação: **{p['taxa']:.1f}%** ➔ Tem {p['aulas']} aulas para apenas {p['livres']} espaços livres na semana).")

    if st.session_state.get('horario_final') is not None:
        df = st.session_state.horario_final
        df['Aula'] = df['Disciplina'] + " \n(" + df['Professor'] + ")"
        
        c_excel, c_pdf = st.columns(2)
        
        output_excel = BytesIO()
        with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
            for turma in sorted(df['Turma'].unique()):
                df_t = df[df['Turma'] == turma]
                df_quadro = df_t.pivot(index='Período', columns='Dia', values='Aula')
                df_quadro = df_quadro.reindex(columns=[d for d in st.session_state.config.get('dias', []) if d in df_quadro.columns])
                df_quadro = df_quadro.reindex(index=range(1, st.session_state.config.get('periodos', 9) + 1)).fillna("")
                df_quadro.to_excel(writer, sheet_name=turma)
                
        with c_excel:
            st.download_button(
                label="📊 Descarregar Quadro em Excel", data=output_excel.getvalue(),
                file_name="Grade_LioChronos_Final.xlsx", use_container_width=True,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        def gerar_pdf(df_horario, config):
            pdf = FPDF(orientation='L', unit='mm', format='A4')
            logo_path = None
            
            if config.get('escola_logo'):
                try:
                    b64_str = config['escola_logo'].split(",")[1]
                    img_data = base64.b64decode(b64_str)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                        tmp.write(img_data)
                        logo_path = tmp.name
                except: pass

            dias_config = config.get('dias', [])
            periodos_config = config.get('periodos', 9)
            
            for turma in sorted(df_horario['Turma'].unique()):
                pdf.add_page()
                if logo_path:
                    pdf.image(logo_path, x=10, y=8, h=20)
                
                pdf.set_font("Arial", 'B', 16)
                pdf.cell(0, 10, txt=limpar_texto_pdf(config.get('escola_nome', 'Horário Escolar')), ln=True, align='C')
                
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 6, txt=limpar_texto_pdf(f"Turma: {turma}"), ln=True, align='C')
                
                pdf.set_font("Arial", 'I', 9)
                pdf.cell(0, 8, txt=limpar_texto_pdf("Horário gerado pelo LioChronos by Liomar Odwazny"), ln=True, align='C')
                pdf.ln(3)

                df_t = df_horario[df_horario['Turma'] == turma]
                df_quadro = df_t.pivot(index='Período', columns='Dia', values='Aula').fillna("")
                dias = [d for d in dias_config if d in df_quadro.columns]
                
                col_w = 260 / (len(dias) + 1)
                
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(20, 10, "Aula", border=1, align='C')
                for d in dias:
                    pdf.cell(col_w, 10, limpar_texto_pdf(d), border=1, align='C')
                pdf.ln()
                
                pdf.set_font("Arial", '', 9)
                for p in range(1, periodos_config + 1):
                    pdf.cell(20, 15, f"{p}o", border=1, align='C')
                    for d in dias:
                        aula_texto = str(df_quadro.at[p, d]) if p in df_quadro.index and d in df_quadro.columns else ""
                        pdf.cell(col_w, 15, limpar_texto_pdf(aula_texto[:45]), border=1, align='C')
                    pdf.ln()

            if logo_path and os.path.exists(logo_path):
                os.remove(logo_path)
                
            return pdf.output(dest='S').encode('latin-1')

        with c_pdf:
            st.download_button(
                label="📄 Descarregar Quadro em PDF", data=gerar_pdf(df, st.session_state.config),
                file_name="Grade_LioChronos_Final.pdf", use_container_width=True,
                mime="application/pdf"
            )
