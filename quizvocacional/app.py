# app.py - Quiz Vocacional Jurídico (versão corrigida para Streamlit + Gemini)
import json
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from fpdf import FPDF

# Tentativa de importar Gemini (google-genai). Se não disponível, fallback silencioso.
try:
    from google import genai
    GEMINI_LIB_DISPONIVEL = True
except Exception:
    GEMINI_LIB_DISPONIVEL = False

# ---------------- CONFIGURAÇÃO BÁSICA ---------------- #

st.set_page_config(
    page_title="Quiz Vocacional Jurídico",
    page_icon="⚖️",
    layout="wide"
)

CARREIRAS = {
    "advocacia": "Advocacia",
    "magistratura": "Magistratura",
    "ministerio_publico": "Ministério Público",
    "consultoria": "Consultoria Jurídica",
}

DESCRICOES_BASE = {
    "advocacia": (
        "A Advocacia envolve a defesa direta de interesses de clientes, atuação em audiências, "
        "negociação de acordos e elaboração de peças processuais. É uma carreira dinâmica, "
        "com forte componente de argumentação, persuasão e contato próximo com pessoas físicas "
        "e jurídicas."
    ),
    "magistratura": (
        "A Magistratura é marcada pela imparcialidade, pelo compromisso com a aplicação correta "
        "do Direito e pela responsabilidade de decidir casos que impactam diretamente a vida das pessoas. "
        "Exige profundo conhecimento jurídico, postura ética e serenidade para lidar com conflitos complexos."
    ),
    "ministerio_publico": (
        "O Ministério Público atua na defesa da ordem jurídica, do regime democrático e dos interesses "
        "sociais e individuais indisponíveis. Envolve combate à criminalidade, promoção de ações civis "
        "públicas, fiscalização do poder público e proteção de direitos coletivos."
    ),
    "consultoria": (
        "A Consultoria Jurídica concentra-se na prevenção de conflitos, elaboração de contratos, pareceres "
        "e estratégias jurídicas para empresas e organizações. Foca em análise técnica, visão de risco, "
        "compliance e planejamento de médio e longo prazo."
    ),
}

# ---------------- FUNÇÕES AUXILIARES ---------------- #

@st.cache_data
def carregar_perguntas():
    """Carrega as perguntas a partir do arquivo JSON (perguntas.json no root)."""
    with open("perguntas.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["perguntas"]


def get_gemini_descricao(carreira_codigo: str) -> str:
    """
    Tenta enriquecer a descrição usando Gemini (google-genai).
    Se a lib não estiver disponível, ou a chave não estiver configurada, retorna a descrição base.
    """
    descricao_base = DESCRICOES_BASE.get(carreira_codigo, "")

    # Se a lib não está instalada, usa a base
    if not GEMINI_LIB_DISPONIVEL:
        return descricao_base

    # Pegar chave: primeiro st.secrets (Streamlit Cloud), depois variáveis de ambiente
    api_key = None
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        api_key = None

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return descricao_base

    # Configura o SDK
    try:
        genai.configure(api_key=api_key)
    except Exception:
        # Se configure não existir ou falhar, tentamos seguir (SDK pode usar Client())
        pass

    carreira_nome = CARREIRAS.get(carreira_codigo, carreira_codigo)

    prompt = (
        f"Você é um orientador vocacional jurídico. Explique de forma clara e objetiva a carreira de {carreira_nome} "
        f"para um estudante de Direito. Use linguagem acessível, em tom encorajador. "
        f"Base: {descricao_base} "
        "Estruture em: visão geral; principais atividades; habilidades importantes; perfil ideal; desafios."
    )

    try:
        # Usa Client + models.generate_content quando disponível
        client = None
        try:
            client = genai.Client()
        except Exception:
            client = None

        if client is not None:
            # generate_content -> retorno com .text (fallback seguro)
            try:
                r = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                texto = getattr(r, "text", None)
                if texto:
                    return texto.strip()
            except Exception:
                # continua para tentativa alternativa abaixo
                pass

        # Alternativa: genai.generate_text / genai.generate (dependendo da versão)
        try:
            # Retorno pode variar; tentamos extrair texto de forma genérica
            res = genai.generate_text(model="gemini-2.5-flash", prompt=prompt)
            texto = getattr(res, "text", None) or str(res)
            if texto:
                return texto.strip()
        except Exception:
            pass

    except Exception:
        # Em qualquer falha, fazemos fallback para base
        return descricao_base

    return descricao_base


def calcular_resultados(respostas_usuario):
    """Calcula pontuação por carreira e retorna (resultados_dict, carreira_final)."""
    resultados = {c: 0 for c in CARREIRAS.keys()}
    for carreira in respostas_usuario.values():
        if carreira in resultados and carreira is not None:
            resultados[carreira] += 1
    carreira_final = max(resultados, key=resultados.get)
    return resultados, carreira_final


def salvar_resultado_csv(nome, resultados, carreira_final):
    """Salva o resultado individual em um CSV (resultados.csv) para o dashboard."""
    total = sum(resultados.values()) or 1
    linha = {
        "timestamp": datetime.now().isoformat(),
        "nome": nome if nome else "",
        "carreira_final": carreira_final,
    }
    for codigo, pontos in resultados.items():
        linha[f"pontos_{codigo}"] = pontos
        linha[f"perc_{codigo}"] = pontos / total * 100

    nova_linha = pd.DataFrame([linha])

    try:
        existente = pd.read_csv("resultados.csv")
        df = pd.concat([existente, nova_linha], ignore_index=True)
    except FileNotFoundError:
        df = nova_linha

    df.to_csv("resultados.csv", index=False)


def gerar_pdf_relatorio(nome, resultados, carreira_final, texto_descricao):
    """Gera um PDF com o resumo do resultado e devolve bytes para download."""
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Relatório - Quiz Vocacional Jurídico", ln=True)

    pdf.set_font("Arial", "", 12)
    if nome:
        pdf.cell(0, 8, f"Participante: {nome}", ln=True)
    pdf.cell(0, 8, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True)

    pdf.ln(4)
    carreira_nome = CARREIRAS.get(carreira_final, carreira_final)
    pdf.multi_cell(0, 8, f"Carreira mais compatível: {carreira_nome}")

    pdf.ln(4)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Pontuações gerais:", ln=True)
    pdf.set_font("Arial", "", 12)

    total = sum(resultados.values()) or 1
    for codigo, pontos in resultados.items():
        nome_c = CARREIRAS.get(codigo, codigo)
        perc = pontos / total * 100
        pdf.cell(0, 8, f"- {nome_c}: {pontos} pontos ({perc:.1f}%)", ln=True)

    pdf.ln(4)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Descrição da carreira:", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 7, texto_descricao)

    pdf_bytes = pdf.output(dest="S").encode("latin-1")
    return pdf_bytes


# ---------------- LAYOUT DA PÁGINA ---------------- #

st.title("⚖️ Quiz Vocacional Jurídico")
st.write(
    "Bem-vindo(a)! Este quiz tem como objetivo ajudar estudantes e profissionais de Direito "
    "a identificarem quais carreiras jurídicas mais combinam com seu perfil."
)

tabs = st.tabs(["📝 Fazer o Quiz", "📊 Dashboard Vocacional"])

# ---------------- ABA 1: QUIZ ---------------- #
with tabs[0]:
    st.subheader("📝 Responda ao Quiz")

    perguntas = carregar_perguntas()

    with st.form("quiz_form"):
        nome = st.text_input("Seu nome (opcional):")
        st.markdown("### Responda às perguntas abaixo:")

        respostas_usuario = {}
        for pergunta in perguntas:
            opcoes_labels = []
            mapa_label_carreira = {}

            for letra, dados in pergunta["opcoes"].items():
                label = f"{letra}) {dados['texto']}"
                opcoes_labels.append(label)
                mapa_label_carreira[label] = dados["carreira"]

            escolha_label = st.radio(
                pergunta["texto"],
                options=opcoes_labels,
                key=f"pergunta_{pergunta['id']}"
            )
            carreira_escolhida = mapa_label_carreira.get(escolha_label)
            respostas_usuario[pergunta["id"]] = carreira_escolhida

        submitted = st.form_submit_button("Ver meu resultado")

    if submitted:
        # Validação: todas respondidas
        if any(v is None for v in respostas_usuario.values()):
            st.error("Por favor, responda todas as perguntas antes de enviar.")
        else:
            resultados, carreira_final = calcular_resultados(respostas_usuario)
            carreira_nome = CARREIRAS[carreira_final]

            st.success(f"Sua carreira mais compatível é: **{carreira_nome}** 🎉")

            # Gráfico de barras com Plotly
            col1, col2 = st.columns([1.2, 1])
            with col1:
                st.markdown("#### Distribuição das suas pontuações")
                df_plot = pd.DataFrame({
                    "Carreira": [CARREIRAS[c] for c in resultados.keys()],
                    "Pontuação": list(resultados.values())
                })
                fig = px.bar(
                    df_plot,
                    x="Carreira",
                    y="Pontuação",
                    title="Perfil vocacional por carreira",
                    text="Pontuação"
                )
                fig.update_traces(textposition="outside")
                fig.update_layout(yaxis=dict(dtick=1))
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("#### Detalhamento numérico")
                total = sum(resultados.values()) or 1
                for codigo, pontos in resultados.items():
                    nome_c = CARREIRAS[codigo]
                    perc = pontos / total * 100
                    st.write(f"**{nome_c}**: {pontos} pontos ({perc:.1f}%)")

            # Descrição da carreira (Gemini + base)
            st.markdown("### Análise da carreira sugerida")
            descricao_carreira = get_gemini_descricao(carreira_final)
            st.write(descricao_carreira)

            # Salvar para estatísticas
            salvar_resultado_csv(nome, resultados, carreira_final)

            # Gerar PDF
            pdf_bytes = gerar_pdf_relatorio(nome, resultados, carreira_final, descricao_carreira)
            st.download_button(
                label="📄 Baixar relatório em PDF",
                data=pdf_bytes,
                file_name="relatorio_quiz_vocacional_juridico.pdf",
                mime="application/pdf"
            )

            st.info(
                "Seu resultado foi salvo anonimamente para compor as estatísticas gerais do dashboard."
            )

# ---------------- ABA 2: DASHBOARD ---------------- #
with tabs[1]:
    st.subheader("📊 Estatísticas gerais do Quiz")

    try:
        df_res = pd.read_csv("resultados.csv")

        st.write(f"Total de respostas registradas: **{len(df_res)}**")

        dist = df_res["carreira_final"].value_counts().rename_axis("carreira").reset_index(name="qtd")
        dist["Carreira"] = dist["carreira"].map(CARREIRAS)
        dist["Percentual"] = dist["qtd"] / dist["qtd"].sum() * 100

        col1, col2 = st.columns([1.2, 1])
        with col1:
            st.markdown("#### Preferência global por carreira")
            fig2 = px.bar(
                dist,
                x="Carreira",
                y="qtd",
                title="Distribuição de carreiras mais compatíveis",
                text="qtd"
            )
            fig2.update_traces(textposition="outside")
            st.plotly_chart(fig2, use_container_width=True)

        with col2:
            st.markdown("#### Percentual de inclinação")
            for _, row in dist.iterrows():
                st.write(f"**{row['Carreira']}**: {row['Percentual']:.1f}% dos participantes")

        st.markdown("#### Dados brutos (para análise)")
        st.dataframe(df_res)

    except FileNotFoundError:
        st.info(
            "Ainda não há dados suficientes para o dashboard. "
            "Peça para mais pessoas responderem o quiz na aba **“Fazer o Quiz”**."
        )

