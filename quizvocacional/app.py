import json
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from fpdf import FPDF

# Import correto do Gemini
try:
    import google.generativeai as genai
    GEMINI_OK = True
except Exception:
    GEMINI_OK = False

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
        "negociação de acordos e elaboração de peças processuais."
    ),
    "magistratura": (
        "A Magistratura é marcada pela imparcialidade e responsabilidade de decidir casos que impactam "
        "diretamente a vida das pessoas."
    ),
    "ministerio_publico": (
        "O Ministério Público atua na defesa da ordem jurídica, do regime democrático e dos interesses "
        "sociais e individuais indisponíveis."
    ),
    "consultoria": (
        "A Consultoria Jurídica concentra-se na prevenção de conflitos, elaboração de pareceres e "
        "estratégias jurídicas para empresas."
    ),
}

# ---------------- FUNÇÕES AUXILIARES ---------------- #

@st.cache_data
def carregar_perguntas():
    with open("perguntas.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["perguntas"]


def get_gemini_descricao(carreira_codigo: str) -> str:
    """Gera descrição com Gemini; se falhar, usa base."""
    base = DESCRICOES_BASE.get(carreira_codigo, "")

    if not GEMINI_OK:
        return base

    api_key = (
        st.secrets.get("GEMINI_API_KEY")
        if "GEMINI_API_KEY" in st.secrets
        else os.environ.get("GEMINI_API_KEY")
    )

    if not api_key:
        return base

    try:
        genai.configure(api_key=api_key)
    except Exception:
        return base

    carreira_nome = CARREIRAS.get(carreira_codigo, carreira_codigo)

    prompt = (
        f"Explique a carreira de {carreira_nome} para um estudante de Direito. "
        f"Baseie-se no texto: {base}. "
        "Estruture em: visão geral; atividades; habilidades importantes; perfil ideal; desafios."
    )

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        resposta = model.generate_content(prompt)
        texto = resposta.text
        return texto.strip()
    except Exception:
        return base


def calcular_resultados(respostas):
    resultados = {c: 0 for c in CARREIRAS}
    for r in respostas.values():
        if r:
            resultados[r] += 1
    carreira_final = max(resultados, key=resultados.get)
    return resultados, carreira_final


def salvar_resultado_csv(nome, resultados, carreira_final):
    total = sum(resultados.values()) or 1

    linha = {
        "timestamp": datetime.now().isoformat(),
        "nome": nome,
        "carreira_final": carreira_final,
    }

    for c, p in resultados.items():
        linha[f"pontos_{c}"] = p
        linha[f"perc_{c}"] = p / total * 100

    df_novo = pd.DataFrame([linha])

    try:
        df_antigo = pd.read_csv("resultados.csv")
        df = pd.concat([df_antigo, df_novo], ignore_index=True)
    except FileNotFoundError:
        df = df_novo

    df.to_csv("resultados.csv", index=False)


def gerar_pdf_relatorio(nome, resultados, carreira_final, descricao):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Relatório - Quiz Vocacional Jurídico", ln=True)

    pdf.set_font("Arial", "", 12)
    if nome:
        pdf.cell(0, 8, f"Participante: {nome}", ln=True)
    pdf.cell(0, 8, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True)

    pdf.ln(4)
    pdf.multi_cell(0, 8, f"Carreira mais compatível: {CARREIRAS[carreira_final]}")
    pdf.ln(4)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Pontuações:", ln=True)

    pdf.set_font("Arial", "", 12)
    total = sum(resultados.values()) or 1
    for c, p in resultados.items():
        pdf.cell(0, 8, f"- {CARREIRAS[c]}: {p} pontos ({p/total*100:.1f}%)", ln=True)

    pdf.ln(4)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Descrição da carreira:", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 7, descricao)

    return pdf.output(dest="S").encode("latin-1")


# ---------------- INTERFACE ---------------- #

st.title("⚖️ Quiz Vocacional Jurídico")

tabs = st.tabs(["📝 Fazer o Quiz", "📊 Dashboard"])

# ---------------- QUIZ ---------------- #
with tabs[0]:
    perguntas = carregar_perguntas()

    with st.form("quiz"):
        nome = st.text_input("Seu nome (opcional):")
        respostas = {}

        for p in perguntas:
            labels = []
            mapa = {}
            for letra, dados in p["opcoes"].items():
                label = f"{letra}) {dados['texto']}"
                labels.append(label)
                mapa[label] = dados["carreira"]

            escolha = st.radio(p["texto"], labels)
            respostas[p["id"]] = mapa[escolha]

        enviado = st.form_submit_button("Ver resultado")

    if enviado:
        resultados, carreira_final = calcular_resultados(respostas)
        carreira_nome = CARREIRAS[carreira_final]

        st.success(f"Carreira mais compatível: **{carreira_nome}**")

        df_plot = pd.DataFrame({
            "Carreira": [CARREIRAS[c] for c in resultados],
            "Pontuação": list(resultados.values())
        })

        fig = px.bar(df_plot, x="Carreira", y="Pontuação")
        st.plotly_chart(fig, use_container_width=True)

        texto = get_gemini_descricao(carreira_final)
        st.markdown("### Análise da carreira sugerida")
        st.write(texto)

        salvar_resultado_csv(nome, resultados, carreira_final)

        pdf_bytes = gerar_pdf_relatorio(nome, resultados, carreira_final, texto)

        st.download_button(
            "📄 Baixar PDF",
            pdf_bytes,
            "relatorio.pdf",
            mime="application/pdf"
        )

# ---------------- DASHBOARD ---------------- #
with tabs[1]:
    try:
        df = pd.read_csv("resultados.csv")

        st.write(f"Total de participantes: **{len(df)}**")

        dist = df["carreira_final"].value_counts().reset_index()
        dist.columns = ["carreira", "qtd"]
        dist["Carreira"] = dist["carreira"].map(CARREIRAS)

        fig = px.bar(dist, x="Carreira", y="qtd")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df)

    except FileNotFoundError:
        st.info("Nenhum dado registrado ainda.")


