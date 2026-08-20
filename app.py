import streamlit as st
import pandas as pd
import requests
import json
import re
from datetime import datetime, timedelta, timezone

# ==========================================
# CONFIGURAÇÃO GERAL
# ==========================================
st.set_page_config(page_title="Dashboard Live Gateway", layout="wide")
st.title("Monitoramento em Tempo Real - Gateway UG65")

try:
    EMAIL = st.secrets["EMAIL"]
    SENHA = st.secrets["SENHA"]
except FileNotFoundError:
    st.error("Credenciais não encontradas. Configure o painel de Secrets no Streamlit Cloud.")
    st.stop()

DEVICE_ID = "3cafb830-5f74-11f1-a47e-b9d94d75df5c"
URL_BASE = "https://thingsboard.nosconectados.com.br"

# ==========================================
# FUNÇÕES DE TRATAMENTO
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

def formatar_nome_chave(chave):
    """Limpa e formata o nome das variáveis para o dashboard."""
    # 1. Ignorar "lixo" de rede LoRaWAN
    lixo = ['applicationID', 'fCnt', 'fPort', 'txInfo']
    if any(ign in chave for ign in lixo):
        return None

    # 2. Renomear termos específicos
    chave_formatada = chave.replace('SALA302', ' (Sala 302)')
    chave_formatada = chave_formatada.replace('energia_ativa_total_', 'Total - Energia Ativa ')
    chave_formatada = chave_formatada.replace('energia_reativa_total_', 'Total - Energia Reativa ')
    chave_formatada = chave_formatada.replace('temperatura_', 'Ambiente - Temperatura ')
    
    # 3. Formatar padrão "Equipamento_Métrica"
    if '_' in chave_formatada and ' (Sala 302)' in chave_formatada and not chave_formatada.startswith('Total') and not chave_formatada.startswith('Ambiente'):
        partes = chave_formatada.split('_', 1)
        equipamento = partes[0]
        # Deixa a métrica mais bonita (ex: energia_ativa -> Energia Ativa)
        metrica = partes[1].replace('_', ' ').title() 
        # Separa palavras grudadas (ex: ArCondicionado -> Ar Condicionado)
        equipamento = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', equipamento)
        
        chave_formatada = f"{equipamento} - {metrica}"
    
    return chave_formatada.strip()

# ==========================================
# AQUISIÇÃO DE DADOS (API THINGSBOARD)
# ==========================================
@st.cache_data(ttl=60) 
def buscar_dados_ao_vivo():
    login_url = f"{URL_BASE}/api/auth/login"
    resposta_login = requests.post(login_url, json={"username": EMAIL, "password": SENHA})
    
    if resposta_login.status_code != 200:
        st.error(f"Falha na autenticação. Status: {resposta_login.status_code}")
        return pd.DataFrame()
        
    jwt_token = resposta_login.json().get("token")
    telemetry_url = f"{URL_BASE}/api/plugins/telemetry/DEVICE/{DEVICE_ID}/values/timeseries"
    headers = {"X-Authorization": f"Bearer {jwt_token}", "Accept": "application/json"}
    
    # Aumentei o limite para garantir que pega os dados de todos os sensores
    params = {"limit": 300} 
    resposta_dados = requests.get(telemetry_url, headers=headers, params=params)
    
    if resposta_dados.status_code != 200:
        st.error(f"Erro ao buscar telemetria. Status: {resposta_dados.status_code}")
        return pd.DataFrame()
        
    dados = resposta_dados.json()
    linhas_tabela = []
    
    # Fuso horário do Brasil (UTC-3)
    fuso_brasil = timezone(timedelta(hours=-3))
    
    for chave, leituras in dados.items():
        for leitura in leituras:
            # Arrumando a Data e Hora
            timestamp_ms = leitura['ts']
            data_hora = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=fuso_brasil).replace(tzinfo=None)
            
            valor = leitura['value']
            
            if isinstance(valor, str) and valor.strip().startswith('{'):
                try:
                    dados_aninhados = json.loads(valor)
                    dados_planos = achatar_dicionario(dados_aninhados, parent_key=chave)
                    for chave_plana, valor_plano in dados_planos.items():
                        nome_limpo = formatar_nome_chave(chave_plana)
                        if nome_limpo: # Se não for lixo de rede, tenta salvar
                            try:
                                linhas_tabela.append({"data_hora": data_hora, "chave": nome_limpo, "valor": float(valor_plano)})
                            except ValueError:
                                pass
                except json.JSONDecodeError:
                    pass
            else:
                nome_limpo = formatar_nome_chave(chave)
                if nome_limpo:
                    try:
                        linhas_tabela.append({"data_hora": data_hora, "chave": nome_limpo, "valor": float(valor)})
                    except ValueError:
                        pass
                    
    return pd.DataFrame(linhas_tabela)

# ==========================================
# INTERFACE DO USUÁRIO
# ==========================================
if st.button("🔄 Puxar Dados Mais Recentes Agora"):
    st.cache_data.clear()

df = buscar_dados_ao_vivo()

if not df.empty:
    df_pivot = df.pivot_table(index='data_hora', columns='chave', values='valor')
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("Filtros de Métricas")
        opcoes_chaves = df_pivot.columns.tolist()
        
        # Filtra opções para deixar de sugestão inicial (ex: coisas do Ar Condicionado)
        padrao = [opt for opt in opcoes_chaves if 'Ar Condicionado' in opt][:2]
        
        chaves_selecionadas = st.multiselect(
            "Selecione as variáveis para o gráfico:",
            options=opcoes_chaves,
            default=padrao if padrao else (opcoes_chaves[:2] if opcoes_chaves else None)
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
    st.warning("Não há dados recentes formatáveis nesta telemetria.")
