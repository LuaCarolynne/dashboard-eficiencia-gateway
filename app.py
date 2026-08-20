import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime

# ==========================================
# CONFIGURAÇÃO GERAL
# ==========================================
st.set_page_config(page_title="Dashboard Live Gateway", layout="wide")
st.title("Monitoramento em Tempo Real - Gateway UG65")

# Puxando as credenciais de forma segura do cofre do Streamlit
try:
    EMAIL = st.secrets["EMAIL"]
    SENHA = st.secrets["SENHA"]
except FileNotFoundError:
    st.error("Credenciais não encontradas. Configure o painel de Secrets no Streamlit Cloud.")
    st.stop()

DEVICE_ID = "3cafb830-5f74-11f1-a47e-b9d94d75df5c"
URL_BASE = "https://thingsboard.nosconectados.com.br"

# ==========================================
# FUNÇÃO PARA ACHATAR OS DADOS KHOMP
# ==========================================
def achatar_dicionario(d, parent_key='', sep='_'):
    """Transforma dicionários aninhados em uma estrutura plana."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(achatar_dicionario(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

# ==========================================
# AQUISIÇÃO DE DADOS (API THINGSBOARD)
# ==========================================
# TTL=60 guarda o resultado em memória por 1 minuto para não sobrecarregar a API
@st.cache_data(ttl=60) 
def buscar_dados_ao_vivo():
    # 1. Realiza o login para obter o Token JWT
    login_url = f"{URL_BASE}/api/auth/login"
    resposta_login = requests.post(login_url, json={"username": EMAIL, "password": SENHA})
    
    if resposta_login.status_code != 200:
        st.error(f"Falha na autenticação com o ThingsBoard. Status: {resposta_login.status_code}")
        return pd.DataFrame()
        
    jwt_token = resposta_login.json().get("token")
    
    # 2. Busca o histórico de telemetria
    telemetry_url = f"{URL_BASE}/api/plugins/telemetry/DEVICE/{DEVICE_ID}/values/timeseries"
    headers = {"X-Authorization": f"Bearer {jwt_token}", "Accept": "application/json"}
    
    # Pegando as últimas 150 leituras para formar um gráfico denso
    params = {"limit": 150} 
    resposta_dados = requests.get(telemetry_url, headers=headers, params=params)
    
    if resposta_dados.status_code != 200:
        st.error(f"Erro ao buscar telemetria. Status: {resposta_dados.status_code}")
        return pd.DataFrame()
        
    dados = resposta_dados.json()
    linhas_tabela = []
    
    # 3. Varre e desempacota o JSON de retorno
    for chave, leituras in dados.items():
        for leitura in leituras:
            timestamp_ms = leitura['ts']
            data_hora = datetime.fromtimestamp(timestamp_ms / 1000.0)
            valor = leitura['value']
            
            # Se for um pacote aninhado (como as métricas de eficiência)
            if isinstance(valor, str) and valor.strip().startswith('{'):
                try:
                    dados_aninhados = json.loads(valor)
                    dados_planos = achatar_dicionario(dados_aninhados, parent_key=chave)
                    
                    for chave_plana, valor_plano in dados_planos.items():
                        try:
                            linhas_tabela.append({
                                "data_hora": data_hora, 
                                "chave": chave_plana, 
                                "valor": float(valor_plano)
                            })
                        except ValueError:
                            pass # Ignora textos (como firmware)
                except json.JSONDecodeError:
                    pass
            # Se for uma métrica direta
            else:
                try:
                    linhas_tabela.append({
                        "data_hora": data_hora, 
                        "chave": chave, 
                        "valor": float(valor)
                    })
                except ValueError:
                    pass
                    
    # Converte tudo para um DataFrame do Pandas
    return pd.DataFrame(linhas_tabela)

# ==========================================
# INTERFACE DO USUÁRIO
# ==========================================

# Botão manual para forçar a busca de dados novos ignorando o tempo do cache
if st.button("🔄 Puxar Dados Mais Recentes Agora"):
    st.cache_data.clear()

df = buscar_dados_ao_vivo()

if not df.empty:
    # "Pivota" os dados para estruturar as chaves como colunas do gráfico
    df_pivot = df.pivot_table(index='data_hora', columns='chave', values='valor')
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("Filtros de Métricas")
        opcoes_chaves = df_pivot.columns.tolist()
        chaves_selecionadas = st.multiselect(
            "Selecione as variáveis para o gráfico:",
            options=opcoes_chaves,
            default=opcoes_chaves[:2] if len(opcoes_chaves) >= 2 else opcoes_chaves
        )
        
    with col2:
        st.subheader("Gráfico Temporal")
        if chaves_selecionadas:
            st.line_chart(df_pivot[chaves_selecionadas])
        else:
            st.info("👈 Selecione pelo menos uma métrica.")
            
    st.divider()
    st.subheader("Log Estruturado da API")
    st.dataframe(df.sort_values(by='data_hora', ascending=False).head(30), use_container_width=True)

else:
    st.warning("Não há dados formatáveis numéricos recentes nesta telemetria.")
