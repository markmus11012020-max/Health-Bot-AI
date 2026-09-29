"""
Health-Bot-AI — Streamlit entry point (thin presentation layer).
All business logic lives under `src/`.
"""
from __future__ import annotations

import streamlit as st

from config.settings import get_settings
from src.core.response_parser import ResponseParser
from src.services.consultation_service import ConsultationInput
from src.services.provider_factory import build_consultation_service
from src.ui.components import (
    render_footer,
    render_header,
    render_provider_badge,
    render_response,
    render_sidebar,
    render_technical_info,
)
from src.ui.styles import CUSTOM_CSS

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

settings = get_settings()
st.set_page_config(
    page_title=settings.app_title,
    page_icon=settings.app_icon,
    layout="centered",
    initial_sidebar_state="collapsed",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session-scoped state
# ---------------------------------------------------------------------------

if "request_count" not in st.session_state:
    st.session_state.request_count = 0

# ---------------------------------------------------------------------------
# Header & sidebar
# ---------------------------------------------------------------------------

render_header(
    title=f"{settings.app_icon} Health-Bot-AI",
    subtitle="Панель ИИ-ассистента OCX | Демонстрация MVP",
)
render_sidebar(st.session_state.request_count)

# ---------------------------------------------------------------------------
# Input form
# ---------------------------------------------------------------------------

st.markdown("### 📝 Входные данные")

crm_context = st.text_area(
    "Контекст сделки AmoCRM",
    placeholder="Пример: Мария оформляет заказ на О-комплекс Детокс за 4500р. "
    "Интересуется доставкой в Самару.",
    height=100,
    help="Вставьте информацию о сделке из AmoCRM: кто клиент, что заказывает, бюджет, комментарии",
)
client_message = st.text_area(
    "Сообщение от клиента",
    placeholder="Пример: Здравствуйте! Хочу узнать, сколько стоит доставка в Самару? "
    "И не будет ли слабости во время очищения?",
    height=100,
    help="Введите сообщение или вопрос клиента",
)

# ---------------------------------------------------------------------------
# Action button
# ---------------------------------------------------------------------------

_, col_mid, _ = st.columns([1, 2, 1])
with col_mid:
    process_button = st.button(
        "🚀 Обработать запрос",
        type="primary",
        use_container_width=True,
        disabled=not (crm_context and client_message),
    )

# ---------------------------------------------------------------------------
# Request handling
# ---------------------------------------------------------------------------

if process_button:
    if not crm_context or not client_message:
        st.error("⚠️ Пожалуйста, заполните оба поля!")
    else:
        service = build_consultation_service(settings)
        with st.spinner("🤖 AI обрабатывает запрос..."):
            outcome = service.run(
                ConsultationInput(
                    crm_context=crm_context,
                    client_message=client_message,
                )
            )
        result = outcome.result

        if result.success and result.result is not None:
            st.session_state.request_count += 1
            provider = result.result.provider
            st.success(f"✅ Ответ готов! Провайдер: {render_provider_badge(provider)}")

            parsed = ResponseParser().parse(result.result.content)
            render_response(parsed)
            render_technical_info(
                provider=provider,
                anonymized=outcome.anonymized_input,
                raw=result.result.content,
            )
        else:
            st.error("❌ Не удалось получить ответ от AI")
            if result.error:
                st.code(result.error, language=None)

render_footer()