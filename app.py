"""
Health-Bot-AI — Streamlit entry point (thin presentation layer).
All business logic lives under `src/`.
"""
from __future__ import annotations

from dataclasses import replace

import streamlit as st

from config.settings import Settings, get_settings
from src.core.audit_log import build_audit_logger
from src.core.db import get_database
from src.core.knowledge_base import KnowledgeBase
from src.core.response_cache import build_cache
from src.core.response_parser import ResponseParser
from src.services.consultation_service import (
    ConsultationInput,
    ConsultationOutcome,
    ConsultationService,
)
from src.services.provider_factory import build_consultation_service
from src.ui.components import (
    render_action_buttons,
    render_advanced_settings,
    render_footer,
    render_header,
    render_history,
    render_provider_badge,
    render_provider_selector,
    render_response,
    render_sidebar,
    render_technical_info,
    reset_form_state,
)
from src.ui.styles import CUSTOM_CSS

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

settings: Settings = get_settings()
st.set_page_config(
    page_title=settings.app_title,
    page_icon=settings.app_icon,
    layout="centered",
    initial_sidebar_state="expanded",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

if "request_count" not in st.session_state:
    st.session_state.request_count = 0
if "history" not in st.session_state:
    st.session_state.history = []  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Shared runtime (Streamlit rerun-safe)
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _shared_cache():
    return build_cache(
        redis_url=settings.redis_url,
        maxsize=settings.cache_maxsize,
        ttl_seconds=settings.cache_ttl_seconds,
    )


@st.cache_resource(show_spinner=False)
def _shared_audit():
    database = get_database(settings.database_url)
    database.init()
    return build_audit_logger(database)


@st.cache_resource(show_spinner=False)
def _shared_kb() -> KnowledgeBase:
    return KnowledgeBase(
        settings.kb_path, top_k=settings.kb_top_k, max_chars=settings.kb_max_chars
    )


@st.cache_resource(show_spinner=False)
def get_runtime(
    provider: str, prompt_variant: str, temperature: float, max_tokens: int
) -> ConsultationService:
    local = replace(
        settings,
        prompt_variant=prompt_variant,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return build_consultation_service(
        local,
        provider_name=provider,
        cache=_shared_cache(),
        audit=_shared_audit(),
        knowledge_base=_shared_kb(),
    )


# ---------------------------------------------------------------------------
# Header & sidebar
# ---------------------------------------------------------------------------

render_header(
    title=f"{settings.app_icon} Health-Bot-AI",
    subtitle="Панель ИИ-ассистента OCX | Production MVP",
)
active_provider = render_provider_selector()
adv = render_advanced_settings(settings)
service = get_runtime(
    active_provider, adv["variant"], adv["temperature"], adv["max_tokens"]
)
render_sidebar(
    st.session_state.request_count,
    active_provider,
    cache_stats=service.cache.stats(),
)

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
    key="crm_context",
)
client_message = st.text_area(
    "Сообщение от клиента",
    placeholder="Пример: Здравствуйте! Хочу узнать, сколько стоит доставка в Самару? "
    "И не будет ли слабости во время очищения?",
    height=100,
    help="Введите сообщение или вопрос клиента",
    key="client_message",
)

process_button, clear_button = render_action_buttons(
    disabled=not (crm_context and client_message),
)

if clear_button:
    reset_form_state()

# ---------------------------------------------------------------------------
# Request handling
# ---------------------------------------------------------------------------

if process_button:
    if not crm_context or not client_message:
        st.error("⚠️ Пожалуйста, заполните оба поля!")
    else:
        payload = ConsultationInput(
            crm_context=crm_context, client_message=client_message
        )
        outcome: ConsultationOutcome | None = None

        try:
            if adv["stream"]:
                with st.spinner("🤖 AI генерирует ответ..."):
                    placeholder = st.empty()
                    stream = service.stream_run(payload)
                    full_text = ""
                    while True:
                        try:
                            token = next(stream)
                        except StopIteration as stop:
                            outcome = stop.value
                            break
                        full_text += token
                        placeholder.markdown(
                            "### 💬 Ответ клиенту (генерация...)\n"
                            f'<div style="background:#E3F2FD;padding:1rem;'
                            f'border-radius:8px;border-left:4px solid #2196F3;'
                            f'white-space:pre-wrap">{full_text}</div>',
                            unsafe_allow_html=True,
                        )
                    placeholder.empty()
            else:
                with st.spinner("🤖 AI обрабатывает запрос..."):
                    outcome = service.run(payload)
        except Exception as exc:  # noqa: BLE001
            st.error(f"❌ Ошибка обработки запроса: {exc}")
            outcome = None

        if outcome is None:
            st.stop()

        if outcome.result.success and outcome.result.result is not None:
            st.session_state.request_count += 1
            provider = outcome.result.result.provider
            model = outcome.result.result.model
            parsed = ResponseParser().parse(outcome.result.result.content)
            st.success(
                f"✅ Ответ готов! Провайдер: {render_provider_badge(provider)} · "
                f"`{model}`"
                + (" · 🟢 из кэша" if outcome.cache_hit else "")
            )
            render_response(
                parsed,
                history_key="main",
                citations=outcome.citations,
                safety_flags=outcome.safety_flags,
            )
            render_technical_info(
                provider=provider,
                model=model,
                anonymized=outcome.anonymized_input,
                raw=outcome.result.result.content,
                citations=outcome.citations,
                safety_flags=outcome.safety_flags,
                latency_ms=outcome.latency_ms,
            )
            st.session_state.history.append(
                {
                    "#": st.session_state.request_count,
                    "provider": provider,
                    "model": model,
                    "client_message": payload.client_message,
                    "crm_context": payload.crm_context,
                    "client_answer": parsed.client_answer,
                    "manager_tip": parsed.manager_tip,
                    "latency_ms": outcome.latency_ms,
                    "response_chars": len(outcome.result.result.content),
                    "cache_hit": outcome.cache_hit,
                    "citations": list(outcome.citations),
                    "safety_flags": list(outcome.safety_flags),
                }
            )
        else:
            st.error("❌ Не удалось получить ответ от AI")
            if outcome.result.error:
                st.code(outcome.result.error, language=None)

# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

render_history(st.session_state.history)
render_footer()
