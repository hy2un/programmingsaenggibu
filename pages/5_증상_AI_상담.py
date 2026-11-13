"""Gemini 건강정보 상담: 환자·의사 아바타로 수정"""

import streamlit as st
from google import genai
from google.genai import types


# 1. AI 상담 페이지 디자인
st.markdown("""
<style>
.stApp {
    background: #fbfdfc;
}

h1, h2, h3 {
    color: #193d34 !important;
    letter-spacing: -.025em;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 18px;
    border-bottom: 1px solid #dcece3;
}

.stTabs [data-baseweb="tab"] {
    color: #52665b !important;
    font-weight: 700;
    padding: 10px 3px 12px;
}

.stTabs [data-baseweb="tab"]:hover,
.stTabs [aria-selected="true"] {
    color: #137f62 !important;
}

.stTabs [data-baseweb="tab-highlight"] {
    background: #137f62 !important;
    height: 3px !important;
    border-radius: 3px !important;
}

.stButton > button,
.stFormSubmitButton > button {
    border-radius: 14px !important;
    font-weight: 700 !important;
}

.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background: #137f62 !important;
    border-color: #137f62 !important;
    color: white !important;
}

.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    background: #0f6b53 !important;
    border-color: #0f6b53 !important;
    color: white !important;
}

.stTextInput input,
div[data-baseweb="select"] > div {
    border-radius: 13px !important;
}

div[data-testid="stAlert"] {
    border-radius: 17px !important;
}

.mc-chat-intro {
    background: #eaf7ef;
    border: 1px solid #d5eadf;
    border-radius: 19px;
    padding: 18px 22px;
    color: #11634e;
    margin: 8px 0 17px;
}

div[data-testid="stChatMessage"] {
    background: #f2faf5;
    border: 1px solid #dcece3;
    border-radius: 16px;
    padding: 10px;
    margin-bottom: 9px;
}

div[data-testid="stChatInput"] {
    border: 1.5px solid #81bda5 !important;
    border-radius: 16px !important;
}

div[data-testid="stChatInput"] button {
    color: #137f62 !important;
}
</style>
""", unsafe_allow_html=True)


# 2. AI 상담 안내
st.title("💬 증상 AI 상담")

st.markdown(
    '<div class="mc-chat-intro">'
    '<strong>무엇이 궁금하신가요?</strong>'
    '<p>증상 관리, 식단, 의약품 성분에 대해 질문해 보세요.</p>'
    '</div>',
    unsafe_allow_html=True,
)

st.caption(
    "메시지는 Google Gemini API로 전송됩니다. "
    "이름·전화번호·주소 등 개인정보를 입력하지 마세요."
)

st.caption(
    "아래 채팅창에서 Enter로 보내고 "
    "Shift+Enter로 줄바꿈할 수 있습니다."
)


# 3. Gemini API 설정
try:
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    model_name = st.secrets.get(
        "GEMINI_MODEL", "gemini-3.6-flash"
    )
except (KeyError, FileNotFoundError):
    api_key = ""
    model_name = "gemini-3.6-flash"

MAX_OUTPUT_TOKENS = 8192

SYSTEM = """당신은 한국어 건강정보 안내 도우미입니다.
- 증상에 대해 일반적인 원인·자가관리·진료가 필요한 상황을 설명합니다.
- 특정 개인에게 의약품 처방, 개인 복용량 결정, 병용 안전성 단정을 하지 않습니다.
- 증상이 불확실하면 필요한 질문을 하며 추측을 진단처럼 말하지 않습니다.
- 흉통, 호흡곤란, 의식 변화, 급격히 악화되는 통증 등은 응급진료가 필요하다고 우선 안내합니다.
- 어린이·노인·반려동물에게 임의 투약을 권하지 않습니다.
- 설명은 명확하고 간결하게 하되 마지막 문장이 끊기지 않도록 합니다.
- 약물과 음식의 상호작용은 확인된 범위에서만 안내합니다.
"""


# 4. 대화 기록 저장
st.session_state.setdefault("gemini_history", [])
st.session_state.setdefault(
    "gemini_last_unfinished", False
)


# 5. 상담 옵션
with st.expander(
    "상담 설정 · 선택 사항",
    expanded=False,
):
    target = st.selectbox(
        "상담 대상",
        ["성인", "청소년·어린이", "고령자", "반려동물"],
        key="gemini_target",
    )

    include_records = st.checkbox(
        "나의 약·질병 기록을 상담에 참고하기",
        value=False,
        key="gemini_records",
    )

    st.caption(
        "이 옵션을 직접 선택한 경우에만 "
        "메인 화면에 등록된 약·질병 이름도 "
        "Gemini로 전송됩니다."
    )


# 6. 대화 기록 초기화
if st.button("대화 지우기", key="gemini_clear"):
    st.session_state.gemini_history = []
    st.session_state.gemini_last_unfinished = False
    st.rerun()

if not api_key:
    st.error(
        "Streamlit Secrets에 GEMINI_API_KEY가 없습니다. "
        "API 키를 등록해 주세요."
    )


# 7. 답변 생성 설정
def make_config():
    return types.GenerateContentConfig(
        system_instruction=SYSTEM,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        thinking_config=types.ThinkingConfig(
            thinking_level="low"
        ),
    )


# 8. 답변 종료 원인 확인
def finish_reason(response):
    candidates = getattr(
        response, "candidates", None
    ) or []

    if not candidates:
        return "UNKNOWN"

    reason = getattr(
        candidates[0], "finish_reason", None
    )

    return getattr(
        reason, "name", str(reason)
    ).split(".")[-1]


# 9. 대화 기록을 Gemini 요청 형식으로 변환
def contents_from(history):
    result = []

    for message in history:
        role = (
            "user"
            if message["role"] == "user"
            else "model"
        )

        result.append(
            types.Content(
                role=role,
                parts=[
                    types.Part(text=message["content"])
                ],
            )
        )

    return result


# 10. Gemini API에 질문 전송
def generate(client, history):
    response = client.models.generate_content(
        model=model_name,
        contents=contents_from(history),
        config=make_config(),
    )

    try:
        answer = response.text or ""
    except (ValueError, AttributeError):
        answer = ""

    return answer, finish_reason(response)


# 11. 출력 제한으로 중단된 답변 이어쓰기
def continue_answer(client, history, partial):
    original = next(
        (
            m["content"]
            for m in reversed(history)
            if m["role"] == "user"
        ),
        "",
    )

    prompt = (
        f"원래 질문: {original}\n\n"
        f"현재까지 답변: {partial}\n\n"
        "출력 제한 때문에 답변이 중단되었습니다. "
        "앞 내용을 반복하지 말고 "
        "자연스럽게 이어서 마무리해 주세요."
    )

    context = (
        history[:-1][-8:]
        + [{"role": "user", "content": prompt}]
    )

    return generate(client, context)


# 12. 기존 메시지 출력
# 사용자: 환자 🤒 / Gemini: 의사 🧑‍⚕️
if not st.session_state.gemini_history:
    st.info(
        "아래 입력창에 증상을 적어 "
        "상담을 시작해 보세요."
    )
else:
    for message in st.session_state.gemini_history:
        avatar = (
            "🤒"
            if message["role"] == "user"
            else "🧑‍⚕️"
        )

        with st.chat_message(
            message["role"],
            avatar=avatar,
        ):
            st.markdown(message["content"])


# 13. 이전에 중단된 답변 다시 이어쓰기
if (
    st.session_state.gemini_last_unfinished
    and api_key
):
    st.warning(
        "이전 답변이 출력 제한으로 중단됐습니다."
    )

    if st.button(
        "↪️ 중단된 답변 이어서 보기",
        type="primary",
    ):
        history = st.session_state.gemini_history

        try:
            with st.spinner(
                "이어지는 답변 생성 중..."
            ):
                client = genai.Client(api_key=api_key)

                extra, reason = continue_answer(
                    client,
                    history,
                    history[-1]["content"],
                )

            if extra.strip():
                history[-1]["content"] += (
                    "\n\n" + extra.strip()
                )

                st.session_state.gemini_last_unfinished = (
                    reason == "MAX_TOKENS"
                )
                st.rerun()
            else:
                st.warning(
                    "추가 답변이 생성되지 않았습니다."
                )

        except Exception as err:
            st.error(
                "추가 답변 요청 실패: "
                f"{type(err).__name__}. "
                "API 키·모델 설정·사용 한도를 확인해 주세요."
            )


# 14. 화면 하단 질문 입력창
question = st.chat_input(
    "증상이나 궁금한 점을 입력하세요...",
    key="gemini_bottom_input",
    max_chars=1500,
    disabled=not bool(api_key),
)


# 15. 질문 전송 및 답변 표시
if question and question.strip():
    history = st.session_state.gemini_history
    prompt = question.strip()

    # 사용자가 동의한 경우에만 약·질병 기록 전달
    if include_records:
        drugs = [
            str(x)
            for x in st.session_state.get(
                "my_drugs", []
            )
        ][:30]

        conditions = [
            str(x)
            for x in st.session_state.get(
                "my_conditions", []
            )
        ][:30]

        prompt += (
            "\n\n[사용자가 공유에 동의한 참고 목록]"
            f"\n약: {', '.join(drugs) or '없음'}"
            f"\n질병: {', '.join(conditions) or '없음'}"
        )

    prompt = f"[상담 대상: {target}]\n{prompt}"

    context = history[-8:] + [
        {"role": "user", "content": prompt}
    ]

    # 사용자 메시지: 환자 이모지
    with st.chat_message(
        "user",
        avatar="🤒",
    ):
        st.markdown(question.strip())

    # AI 답변: 의사 이모지
    with st.chat_message(
        "assistant",
        avatar="🧑‍⚕️",
    ):
        try:
            with st.spinner("답변 작성 중..."):
                client = genai.Client(api_key=api_key)

                answer, reason = generate(
                    client,
                    context,
                )

                if (
                    reason == "MAX_TOKENS"
                    and answer.strip()
                ):
                    extra, reason = continue_answer(
                        client,
                        context,
                        answer,
                    )

                    if extra.strip():
                        answer = (
                            answer.rstrip()
                            + "\n\n"
                            + extra.strip()
                        )

            if answer.strip():
                st.markdown(answer)

                history.extend([
                    {
                        "role": "user",
                        "content": question.strip(),
                    },
                    {
                        "role": "assistant",
                        "content": answer,
                    },
                ])

                st.session_state.gemini_last_unfinished = (
                    reason == "MAX_TOKENS"
                )
            else:
                st.warning(
                    "답변을 받지 못했습니다. "
                    "질문을 바꾸거나 다시 시도해 주세요."
                )

        except Exception as err:
            st.error(
                "Gemini 연결 오류: "
                f"{type(err).__name__}. "
                "API 설정이나 사용 한도를 확인해 주세요."
            )
