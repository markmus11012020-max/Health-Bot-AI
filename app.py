"""
Health-Bot-AI — Streamlit entry point (thin presentation layer).
All business logic lives under `src/`.
"""
from __future__ import annotations

import streamlit as st

from config.settings import Settings, get_settings
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
    render_streaming_response,
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
    initial_sidebar_state="collapsed",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session-scoped state
# ---------------------------------------------------------------------------

if "request_count" not in st.session_state:
    st.session_state.request_count = 0
if "history" not in st.session_state:
    st.session_state.history = []  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Header & sidebar
# ---------------------------------------------------------------------------

render_header(
    title=f"{settings.app_icon} Health-Bot-AI",
    subtitle="Панель ИИ-ассистента OCX | Демонстрация MVP | Тестовый режим",
)
active_provider = render_provider_selector()
adv = render_advanced_settings(settings)
render_sidebar(
    st.session_state.request_count,
    active_provider,
    cache_size=0,  # обновим ниже после построения сервиса
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

# ---------------------------------------------------------------------------
# Action buttons (process + clear)
# ---------------------------------------------------------------------------

process_button, clear_button = render_action_buttons(
    disabled=not (crm_context and client_message),
)

# «Очистить форму» проверяем ДО «Обработать запрос» — иначе при одновременном
# нажатии (теоретически возможно в одном rerun) мог бы сработать и запрос.
if clear_button:
    reset_form_state()

# ---------------------------------------------------------------------------
# Request handling
# ---------------------------------------------------------------------------

if process_button:
    if not crm_context or not client_message:
        st.error("⚠️ Пожалуйста, заполните оба поля!")
    else:
        # Применяем override из UI к settings (на одну сессию).
        overridden = Settings(
            aitunnel_api_key=settings.aitunnel_api_key,
            aitunnel_base_url=settings.aitunnel_base_url,
            aitunnel_model=settings.aitunnel_model,
            yandex_api_key=settings.yandex_api_key,
            yandex_iam_token=settings.yandex_iam_token,
            yandex_folder_id=settings.yandex_folder_id,
            yandex_gpt_url=settings.yandex_gpt_url,
            yandex_gpt_model=settings.yandex_gpt_model,
            yandex_timeout_s=settings.yandex_timeout_s,
            temperature=adv["temperature"],
            max_tokens=adv["max_tokens"],
            request_timeout=settings.request_timeout,
            max_retries=settings.max_retries,
            app_title=settings.app_title,
            app_icon=settings.app_icon,
            prompt_variant=adv["variant"],
        )
        service: ConsultationService = build_consultation_service(
            overridden, provider_name=active_provider
        )
        cache_size = service.cache.stats()["size"]
        # Обновим метрику кэша в сайдбаре после построения сервиса.
        render_sidebar(
            st.session_state.request_count, active_provider, cache_size=cache_size
        )

        payload = ConsultationInput(
            crm_context=crm_context, client_message=client_message
        )

        outcome: ConsultationOutcome
        if adv["stream"]:
            # ----- Стриминг -----
            with st.spinner("🤖 AI генерирует ответ..."):
                ph_client = st.empty()
                ph_manager = st.empty()
                gen = service.stream_run(payload)
                full_text = ""
                try:
                    while True:
                        token = next(gen)
                        full_text += token
                        ph_client.markdown(
                            "### 💬 Ответ клиенту\n"
                            f'<div style="background:#E3F2FD;padding:1rem;'
                            f'border-radius:8px;border-left:4px solid #2196F3;'
                            f'white-space:pre-wrap">{full_text}</div>',
                            unsafe_allow_html=True,
                        )
                except StopIteration as stop:
                    outcome = stop.value

            if outcome.result.success and outcome.result.result is not None:
                st.session_state.request_count += 1
                provider = outcome.result.result.provider
                st.success(
                    f"✅ Ответ готов! Провайдер: {render_provider_badge(provider)}"
                    + (" · 🟢 из кэша" if outcome.cache_hit else "")
                )
                parsed = ResponseParser().parse(outcome.result.result.content)
                render_streaming_response(ph_client, ph_manager, parsed)
                # Кнопки копирования отдельным блоком (всегда после стрима)
                with st.container():
                    render_response(parsed, history_key="stream")
                render_technical_info(
                    provider=provider,
                    anonymized=outcome.anonymized_input,
                    raw=outcome.result.result.content,
                )
                st.session_state.history.append(
                    {
                        "#": st.session_state.request_count,
                        "provider": provider,
                        "client_message": payload.client_message,
                        "crm_context": payload.crm_context,
                        "client_answer": parsed.client_answer,
                        "manager_tip": parsed.manager_tip,
                        "latency_ms": 0,  # в стриме не замеряем точно
                        "response_chars": len(outcome.result.result.content),
                        "cache_hit": outcome.cache_hit,
                    }
                )
            else:
                st.error("❌ Не удалось получить ответ от AI")
                if outcome.result.error:
                    st.code(outcome.result.error, language=None)
        else:
            # ----- Не-стрим режим -----
            with st.spinner("🤖 AI обрабатывает запрос..."):
                outcome = service.run(payload)

            if outcome.result.success and outcome.result.result is not None:
                st.session_state.request_count += 1
                provider = outcome.result.result.provider
                st.success(
                    f"✅ Ответ готов! Провайдер: {render_provider_badge(provider)}"
                    + (" · 🟢 из кэша" if outcome.cache_hit else "")
                )

                parsed = ResponseParser().parse(outcome.result.result.content)
                render_response(parsed, history_key="nostream")
                render_technical_info(
                    provider=provider,
                    anonymized=outcome.anonymized_input,
                    raw=outcome.result.result.content,
                )
                # История
                st.session_state.history.append(
                    {
                        "#": st.session_state.request_count,
                        "provider": provider,
                        "client_message": payload.client_message,
                        "crm_context": payload.crm_context,
                        "client_answer": parsed.client_answer,
                        "manager_tip": parsed.manager_tip,
                        "latency_ms": 0,
                        "response_chars": len(outcome.result.result.content),
                        "cache_hit": outcome.cache_hit,
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