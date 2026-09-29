"""Reusable Streamlit rendering helpers."""
from __future__ import annotations

from typing import Iterable

import streamlit as st

from src.core.response_parser import ParsedResponse
from src.services.provider_factory import DEFAULT_PROVIDER, PROVIDER_REGISTRY
from src.ui.styles import FOOTER_HTML


def render_header(*, title: str, subtitle: str) -> None:
    st.markdown(f'<h1 class="main-header">{title}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="sub-header">{subtitle}</p>', unsafe_allow_html=True)
    st.markdown(
        '<div class="compliance-badge">🔒 Соответствие 152-ФЗ: '
        "персональные данные анонимизируются перед отправкой в LLM</div>",
        unsafe_allow_html=True,
    )


_PROVIDER_LABELS = {
    "aitunnel": "🟢 AITunnel",
    "yandex": "🟡 YandexGPT",
}


def render_provider_selector() -> str:
    """Render a sidebar radio for choosing the active AI provider.

    Returns the registry key (e.g. ``"aitunnel"``).
    Persists the choice in ``st.session_state`` so reruns keep it stable.
    """
    with st.sidebar:
        st.markdown("### 🔧 Провайдер AI")
        st.caption("⚠️ Тестовый режим: активен только один провайдер")
        options = list(PROVIDER_REGISTRY.keys())
        default_index = options.index(DEFAULT_PROVIDER) if DEFAULT_PROVIDER in options else 0
        choice = st.radio(
            "Выберите провайдера:",
            options=options,
            format_func=lambda key: _PROVIDER_LABELS.get(key, key),
            index=default_index,
            key="provider_choice",
        )
        return choice


def render_sidebar(request_count: int, active_provider: str) -> None:
    with st.sidebar:
        st.markdown("### 📋 Инструкция")
        st.markdown(
            "**1.** Заполните контекст сделки из AmoCRM\n\n"
            "**2.** Введите сообщение клиента\n\n"
            "**3.** Нажмите «Обработать запрос»\n\n"
            "**4.** Скопируйте ответ для клиента"
        )
        st.markdown("---")
        st.markdown("### 🔧 Провайдер AI")
        label = _PROVIDER_LABELS.get(active_provider, active_provider)
        st.markdown(f"**Активный:** {label}")
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