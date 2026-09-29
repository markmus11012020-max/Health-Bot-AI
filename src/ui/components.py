"""Reusable Streamlit rendering helpers."""
from __future__ import annotations

from typing import Iterable

import streamlit as st

from src.core.response_parser import ParsedResponse
from src.ui.styles import FOOTER_HTML


def render_header(*, title: str, subtitle: str) -> None:
    st.markdown(f'<h1 class="main-header">{title}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="sub-header">{subtitle}</p>', unsafe_allow_html=True)
    st.markdown(
        '<div class="compliance-badge">🔒 Соответствие 152-ФЗ: '
        "персональные данные анонимизируются перед отправкой в LLM</div>",
        unsafe_allow_html=True,
    )


def render_sidebar(request_count: int) -> None:
    with st.sidebar:
        st.markdown("### 📋 Инструкция")
        st.markdown(
            "**1.** Заполните контекст сделки из AmoCRM\n\n"
            "**2.** Введите сообщение клиента\n\n"
            "**3.** Нажмите «Обработать запрос»\n\n"
            "**4.** Скопируйте ответ для клиента"
        )
        st.markdown("---")
        st.markdown("### 🔧 Провайдеры AI")
        st.markdown("- **Основной:** AITunnel\n- **Fallback:** YandexGPT")
        st.markdown("---")
        st.markdown("### 📊 Статистика сессии")
        st.metric("Запросов обработано", request_count)


def render_response(parsed: ParsedResponse) -> None:
    """Display client answer + manager tip + copy button."""
    st.markdown("---")
    st.markdown("### 💬 Ответ клиенту")

    col_copy, _ = st.columns([1, 4])
    with col_copy:
        if st.button("📋 Копировать ответ", key="copy_client"):
            try:
                import pyperclip

                pyperclip.copy(parsed.client_answer)
                st.toast("✓ Ответ скопирован!")
            except Exception as exc:  # noqa: BLE001
                st.warning(f"Не удалось скопировать: {exc}")

    st.info(parsed.client_answer)

    st.markdown("---")
    st.markdown("### 💼 Подсказка по допродажам (для менеджера)")
    if "Допродажа не требуется" in parsed.manager_tip:
        st.info("💡 " + parsed.manager_tip)
    else:
        st.success(parsed.manager_tip)


def render_technical_info(*, provider: str, anonymized: str, raw: str) -> None:
    with st.expander("🔍 Техническая информация (для разработчика)"):
        st.markdown("**Анонимизированные данные (152-ФЗ):**")
        st.code(anonymized, language=None)
        st.markdown(f"**Провайдер:** {provider}")
        st.markdown("**Полный ответ AI:**")
        st.code(raw, language=None)


def render_footer() -> None:
    st.markdown("---")
    st.markdown(FOOTER_HTML, unsafe_allow_html=True)


def render_provider_badge(provider: str) -> str:
    """Color-code provider badges."""
    return "🟢 " + provider if "AITunnel" in provider else "🟡 " + provider