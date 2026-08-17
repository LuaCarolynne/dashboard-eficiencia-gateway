import streamlit as st
import sqlite3
import pandas as pd

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Dashboard Gateway", layout="wide")
st.title("Monitoramento de Telemetria e Eficiência Energética")
st.markdown("Dashboard local lendo dados estruturados do SQLite")

# ==========================================
# FUNÇÃO PARA CARREGAR DADOS
# ==========================================
def carregar_dados():
    conn = sqlite3.connect('banco_dados.sqlite')
    df = pd.read_sql_query("SELECT * FROM telemetria_gateway", conn)
    conn.close()
    return df

df = carregar_dados()

if not df.empty:
    # Converte a coluna de data para o formato de tempo do Pandas
    df['data_hora'] = pd.to_datetime(df['data_hora'])
    
    # "Pivota" os dados para que cada chave de leitura se torne uma coluna no gráfico
    df_pivot = df.pivot_table(index='data_hora', columns='chave', values='valor')
    
    # ==========================================
    # LAYOUT DO DASHBOARD
    # ==========================================
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("Filtros de Métricas")
        st.write("Selecione as variáveis que deseja cruzar no gráfico:")
        
        # Pega todas as chaves disponíveis no banco (ex: circuitos_A_corrente)
        opcoes_chaves = df_pivot.columns.tolist()
        
        # Cria um menu de múltipla escolha
        chaves_selecionadas = st.multiselect(
            "Métricas:",
            options=opcoes_chaves,
            default=opcoes_chaves[:2] if len(opcoes_chaves) >= 2 else opcoes_chaves
        )
    
    with col2:
        st.subheader("Visualização Temporal")
        if chaves_selecionadas:
            # Filtra e desenha o gráfico apenas com as colunas que você selecionou
            df_filtrado = df_pivot[chaves_selecionadas]
            st.line_chart(df_filtrado)
        else:
            st.info("👈 Selecione pelo menos uma métrica no menu ao lado para gerar o gráfico.")
    
    st.divider()
    
    # ==========================================
    # TABELA DE DADOS BRUTOS
    # ==========================================
    st.subheader("Últimos Registros Brutos no Banco (SQLite)")
    # Mostra a tabela invertida para ver os dados mais recentes primeiro
    st.dataframe(df.sort_values(by='data_hora', ascending=False).head(50), use_container_width=True)

else:
    st.warning("Nenhum dado encontrado no banco SQLite. Execute o script de coleta primeiro.")