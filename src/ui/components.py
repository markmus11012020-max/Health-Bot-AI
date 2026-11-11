"""Reusable Streamlit rendering helpers."""
from __future__ import annotations

from collections.abc import Iterable

import streamlit as st

from config.prompts import list_variants
from config.settings import Settings
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
    st.caption(
        "Ответы носят информационный характер и не являются медицинской "
        "рекомендацией. Менеджер проверяет ответ перед отправкой клиенту."
    )


_PROVIDER_LABELS = {
    "aitunnel": "🟢 AITunnel",
    "yandex": "🟡 YandexGPT",
}

_VARIANT_LABELS = {
    "standard": "💚 Standard — базовый дружелюбный",
    "expert": "🔬 Expert — аргументированный, клинический",
    "warm": "💛 Warm — тёплый, миссия OCX",
}

_SAFETY_MESSAGES = {
    "prompt_injection_blocked": "🛑 Запрос заблокирован: обнаружена попытка prompt injection.",
    "prompt_injection_suspected": "⚠️ В запросе есть подозрительные инструкции; ответ проверен guardrails.",
    "medical_red_flag": "🩺 Обнаружен медицинский red flag: рекомендуется консультация врача.",
    "medical_claim_softened": "✏️ Формулировки ответа смягчены правилами медицинской безопасности.",
}


def render_provider_selector() -> str:
    """Render a sidebar radio for choosing the active AI provider."""
    with st.sidebar:
        st.markdown("### 🔧 Провайдер AI")
        st.caption("Production MVP: основной провайдер + резервный fallback")
        options = list(PROVIDER_REGISTRY.keys())
        default_index = (
            options.index(DEFAULT_PROVIDER) if DEFAULT_PROVIDER in options else 0
        )
        choice = st.radio(
            "Выберите провайдера:",
            options=options,
            format_func=lambda key: _PROVIDER_LABELS.get(key, key),
            index=default_index,
            key="provider_choice",
        )
        return choice


def render_advanced_settings(settings: Settings) -> dict:
    """Сайдбар: расширенные параметры генерации (перекрывают .env на сессию)."""
    with st.sidebar:
        st.markdown("---")
        with st.expander("⚙️ Расширенные параметры", expanded=False):
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=1.0,
                value=float(settings.temperature),
                step=0.05,
                help="0 = строго по БЗ, 1 = креативнее. По умолчанию 0.2.",
                key="adv_temperature",
            )
            max_tokens = st.slider(
                "Max tokens",
                min_value=200,
                max_value=2000,
                value=int(settings.max_tokens),
                step=100,
                key="adv_max_tokens",
            )
            variants = list_variants()
            current_variant = st.session_state.get("adv_variant", settings.prompt_variant)
            if current_variant not in variants:
                current_variant = variants[0]
            variant = st.selectbox(
                "Вариант промпта (A/B)",
                options=variants,
                index=variants.index(current_variant),
                format_func=lambda k: _VARIANT_LABELS.get(k, k),
                key="adv_variant",
            )
            use_stream = st.checkbox(
                "⚡ Стриминг (мгновенный отклик)",
                value=True,
                key="adv_stream",
                help="Показывать токены по мере генерации. Снимите, если провайдер не поддерживает стрим.",
            )
        return {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "variant": variant,
            "stream": use_stream,
        }


def render_sidebar(
    request_count: int, active_provider: str, cache_stats: dict | None = None
) -> None:
    cache_stats = cache_stats or {}
    with st.sidebar:
        st.markdown("### 📋 Инструкция")
        st.markdown(
            "**1.** Заполните контекст сделки из AmoCRM\n\n"
            "**2.** Введите сообщение клиента\n\n"
            "**3.** Нажмите «Обработать запрос»\n\n"
            "**4.** Проверьте ответ и скопируйте его клиенту"
        )
        st.markdown("---")
        st.markdown("### 🔧 Провайдер AI")
        st.markdown(f"**Активный:** {_PROVIDER_LABELS.get(active_provider, active_provider)}")
        st.markdown("---")
        st.markdown("### 📊 Статистика сессии")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Запросов", request_count)
        with col2:
            st.metric("Кэш", int(cache_stats.get("size", 0)))
        if cache_stats:
            st.caption(
                f"TTL: {cache_stats.get('ttl_seconds', 0)} с · "
                f"hit rate: {float(cache_stats.get('hit_rate', 0)):.0%}"
            )


def _safe_copy_to_clipboard(text: str, *, success_message: str) -> None:
    try:
        import pyperclip

        pyperclip.copy(text)
        st.toast(success_message)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Не удалось скопировать: {exc}")


def _render_safety_flags(flags: Iterable[str]) -> None:
    for flag in dict.fromkeys(flags):
        message = _SAFETY_MESSAGES.get(flag)
        if message:
            st.warning(message)


def render_response(
    parsed: ParsedResponse,
    *,
    history_key: str | None = None,
    citations: Iterable[str] = (),
    safety_flags: Iterable[str] = (),
) -> None:
    """Показать ответ, источники, safety-флаги и кнопки копирования."""
    st.markdown("---")
    st.markdown("### 💬 Ответ клиенту")

    col_copy, _ = st.columns([1, 4])
    with col_copy:
        if st.button("📋 Копировать ответ", key=f"copy_client_{history_key or 'main'}"):
            _safe_copy_to_clipboard(
                parsed.client_answer, success_message="✓ Ответ скопирован!"
            )

    st.info(parsed.client_answer)
    _render_safety_flags(safety_flags)

    sources = tuple(dict.fromkeys(citations))
    if sources:
        st.caption("📚 Источники: " + "; ".join(sources))

    st.markdown("---")
    st.markdown("### 💼 Подсказка по допродажам (для менеджера)")
    if not parsed.needs_upsell:
        st.info("💡 " + parsed.manager_tip)
    else:
        st.success(parsed.manager_tip)

    col_copy_mgr, _ = st.columns([1, 4])
    with col_copy_mgr:
        if st.button(
            "📋 Копировать подсказку", key=f"copy_manager_{history_key or 'main'}"
        ):
            _safe_copy_to_clipboard(
                parsed.manager_tip,
                success_message="✓ Подсказка скопирована!",
            )


def render_streaming_response(
    placeholder_client, placeholder_manager, parsed: ParsedResponse
) -> None:
    """Финальный рендер после стриминга (совместимость со старым API)."""
    placeholder_client.markdown("### 💬 Ответ клиенту")
    placeholder_client.info(parsed.client_answer)
    placeholder_manager.markdown("### 💼 Подсказка по допродажам (для менеджера)")
    if not parsed.needs_upsell:
        placeholder_manager.info("💡 " + parsed.manager_tip)
    else:
        placeholder_manager.success(parsed.manager_tip)


def render_history(history: list[dict]) -> None:
    """Свернутая история прошлых обращений в текущей сессии."""
    if not history:
        return
    st.markdown("---")
    st.markdown(f"### 🕓 История сессии ({len(history)})")
    for entry in reversed(history[-10:]):  # последние 10
        label = (
            f"#{entry['#']} · {entry['provider']} · "
            f"{entry['client_message'][:60]}"
            f"{'…' if len(entry['client_message']) > 60 else ''}"
        )
        with st.expander(label, expanded=False):
            st.markdown("**Сообщение клиента:**")
            st.text(entry["client_message"])
            st.markdown("**Контекст AmoCRM:**")
            st.text(entry["crm_context"])
            st.markdown("---")
            st.markdown("**💬 Ответ клиенту:**")
            st.info(entry["client_answer"])
            st.markdown("**💼 Подсказка менеджеру:**")
            st.success(entry["manager_tip"])
            if entry.get("citations"):
                st.caption("📚 Источники: " + "; ".join(entry["citations"]))
            st.caption(
                f"⏱ {entry['latency_ms']} мс · "
                f"📊 {entry['response_chars']} символов · "
                f"{'🟢 кэш' if entry['cache_hit'] else '🔵 AI'}"
            )


def render_technical_info(
    *,
    provider: str,
    model: str,
    anonymized: str,
    raw: str,
    citations: Iterable[str] = (),
    safety_flags: Iterable[str] = (),
    latency_ms: int = 0,
) -> None:
    with st.expander("🔍 Техническая информация (для разработчика)"):
        st.markdown("**Анонимизированные данные (152-ФЗ):**")
        st.code(anonymized, language=None)
        st.markdown(f"**Провайдер:** {provider}")
        st.markdown(f"**Модель:** `{model}`")
        st.markdown(f"**Latency:** {latency_ms} мс")
        if citations:
            st.markdown("**Источники:** " + "; ".join(dict.fromkeys(citations)))
        if safety_flags:
            st.markdown("**Safety flags:** " + ", ".join(dict.fromkeys(safety_flags)))
        st.markdown("**Полный ответ AI (после guardrails):**")
        st.code(raw, language=None)


def render_footer() -> None:
    st.markdown("---")
    st.markdown(FOOTER_HTML, unsafe_allow_html=True)


def render_provider_badge(provider: str) -> str:
    return "🟢 " + provider if "AITunnel" in provider else "🟡 " + provider


# ---------------------------------------------------------------------------
# Form actions
# ---------------------------------------------------------------------------

_FORM_STATE_KEYS: tuple[str, ...] = (
    "crm_context",
    "client_message",
    "last_outcome",
    "last_raw_response",
    "last_anonymized",
    "last_provider",
)


def render_action_buttons(*, disabled: bool) -> tuple[bool, bool]:
    """Кнопки действий: «Обработать запрос» + «Очистить форму»."""
    col_process, col_clear = st.columns(2)
    with col_process:
        process_clicked = st.button(
            "🚀 Обработать запрос",
            type="primary",
            use_container_width=True,
            disabled=disabled,
            key="action_process",
        )
    with col_clear:
        clear_clicked = st.button(
            "🧹 Очистить форму",
            use_container_width=True,
            key="action_clear",
            help="Сбросить поля ввода, результат генерации и технический лог",
        )
    return process_clicked, clear_clicked


def reset_form_state(extra_keys: Iterable[str] = ()) -> None:
    """Удалить ключи формы из session_state и принудительно перезагрузить UI."""
    for key in (*_FORM_STATE_KEYS, *extra_keys):
        st.session_state.pop(key, None)
    st.toast("🧹 Форма очищена", icon="✅")
    st.rerun()
