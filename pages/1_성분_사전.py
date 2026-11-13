"""성분 사전: 성분 검색, 관련 제품, 의약품 용어, 출처 확인."""
from urllib.parse import quote

import pandas as pd
import streamlit as st

from drug_data_tools import (
    load_data,
    split_ingredients,
)

st.markdown("""<style>
.stApp {background:#fbfdfc;}
h1,h2,h3 {color:#193d34 !important;letter-spacing:-.025em;}
.stTabs [data-baseweb="tab-list"] {
 gap:18px;border-bottom:1px solid #dcece3;
}
.stTabs [data-baseweb="tab"] {
 color:#52665b !important;font-weight:700;padding:10px 3px 12px;
}
.stTabs [data-baseweb="tab"]:hover,
.stTabs [aria-selected="true"] {color:#137f62 !important;}
.stTabs [data-baseweb="tab-highlight"] {
 background:#137f62 !important;height:3px !important;
 border-radius:3px !important;
}
.stButton > button,.stFormSubmitButton > button {
 border-radius:14px !important;font-weight:700 !important;
}
.stButton > button[kind="primary"] {
 background:#137f62 !important;
 border-color:#137f62 !important;color:white !important;
}
.stTextInput input,div[data-baseweb="select"] > div {
 border-radius:13px !important;
}
div[data-testid="stDataFrame"] {
 border-radius:14px;overflow:hidden;
}
div[data-testid="stAlert"] {border-radius:17px !important;}
</style>""", unsafe_allow_html=True)


def information_search(name):
    """약학정보원에서 성분 이름을 검색하는 링크."""
    return (
        "https://www.google.com/search?q="
        + quote(f'site:health.kr "{name}"')
    )


def add_source_columns(df, key_col):
    result = df.copy().fillna("")
    source = result.get(
        "출처URL",
        pd.Series("", index=result.index),
    ).astype(str).str.strip()

    # 기존 CSV의 개별 제품 URL과
    # 성분 정보 검색 링크를 구분한다.
    result["기존 출처 링크"] = source.where(
        source.str.contains(
            "/drug/", regex=False
        ),
        "",
    )
    result["성분 정보 검색"] = (
        result[key_col]
        .astype(str)
        .map(information_search)
    )
    result["출처 상태"] = source.map(
        lambda url: (
            "제품 정보 링크·성분 연관성 확인 필요"
            if "/drug/" in url
            else "개별 출처 검증 필요"
        )
    )
    return result


st.title("📘 성분 사전")
st.caption(
    "성분명·분류·설명을 검색하고 "
    "관련 제품 및 의약품 용어를 확인하세요."
)

try:
    drugs, ingredients = load_data()
except (
    FileNotFoundError,
    ValueError,
    KeyError,
    pd.errors.ParserError,
) as err:
    st.error(f"CSV 파일을 확인해 주세요: {err}")
    st.stop()

keyword = st.text_input(
    "성분명·분류·설명 검색",
    placeholder="예: 아세트아미노펜, 항히스타민, 진해",
)

result = ingredients.copy().fillna("")

if keyword.strip():
    mask = result[
        ["성분명", "분류", "설명"]
    ].astype(str).apply(
        lambda s: s.str.contains(
            keyword.strip(),
            case=False,
            regex=False,
            na=False,
        )
    ).any(axis=1)
    result = result[mask]

st.subheader("전체 성분 목록")
st.write(
    f"조회된 성분 **{len(result)}개 / "
    f"전체 {len(ingredients)}개**"
)

if result.empty:
    st.info(
        "검색 조건에 해당하는 성분이 없습니다. "
        "검색어를 바꿔 주세요."
    )
else:
    shown = add_source_columns(
        result, "성분명"
    )
    st.dataframe(
        shown[
            [
                "성분명",
                "분류",
                "설명",
                "기존 출처 링크",
                "성분 정보 검색",
                "출처 상태",
            ]
        ],
        hide_index=True,
        use_container_width=True,
        height=375,
        column_config={
            "기존 출처 링크": (
                st.column_config.LinkColumn(
                    "기존 제품 링크"
                )
            ),
            "성분 정보 검색": (
                st.column_config.LinkColumn(
                    "성분별 정보 검색"
                )
            ),
        },
    )

    chosen = st.selectbox(
        "해당 성분이 포함된 등록 의약품 확인",
        ["선택 안 함"] + shown["성분명"].tolist(),
    )

    if chosen != "선택 안 함":
        products = sorted(set(
            str(row["제품명"])
            for _, row in drugs.iterrows()
            if chosen in split_ingredients(
                row["성분"]
            )
        ))

        if products:
            st.write(
                "**등록 의약품:** "
                + ", ".join(products)
            )
        else:
            st.info(
                "등록된 제품 중 해당 성분을 "
                "포함한 제품을 찾지 못했습니다."
            )

st.caption(
    "'성분별 정보 검색'은 이름을 검색하는 링크이며 "
    "검증된 개별 원문 출처를 뜻하지 않습니다."
)

# 의약품 용어 해설 13개
GLOSSARY = [
    (
        "완하",
        "배변을 쉽게 하도록 변을 부드럽게 하거나 "
        "장운동을 돕는 작용. 완하제는 변비에 사용합니다.",
    ),
    (
        "완화",
        "통증이나 불편감, 긴장 등의 정도를 "
        "줄이는 것을 뜻합니다.",
    ),
    (
        "항히스타민",
        "히스타민 작용을 억제해 재채기·콧물·가려움 등의 "
        "알레르기 증상을 줄이는 약물군입니다.",
    ),
    (
        "거담",
        "가래를 묽게 하거나 배출되도록 돕는 작용입니다.",
    ),
    (
        "진해",
        "기침을 줄이거나 억제하는 작용입니다.",
    ),
    (
        "비충혈 완화",
        "부은 코 점막의 혈관 수축 등을 통해 "
        "코막힘을 줄이는 작용입니다.",
    ),
    (
        "비스테로이드성 소염진통제(NSAIDs)",
        "스테로이드가 아닌 통증·염증·발열 완화 약물군으로 "
        "위장관·신장 부작용에 주의합니다.",
    ),
    (
        "이뇨",
        "소변 배출을 늘리는 작용입니다.",
    ),
    (
        "생약 성분",
        "식물·동물·광물 등의 천연 유래 약용 원료이며, "
        "천연이라는 이유로 항상 안전하지는 않습니다.",
    ),
    (
        "담즙산",
        "간에서 만들어져 지방 소화·흡수를 돕는 물질로 "
        "일부 관련 약물이 치료에 쓰입니다.",
    ),
    (
        "청량 성분",
        "멘톨처럼 시원한 감각을 주는 성분이며 "
        "청량감 자체가 치료 효과를 뜻하지는 않습니다.",
    ),
    (
        "코르티코스테로이드",
        "염증·면역 반응을 조절하는 스테로이드 계열 약물로 "
        "제형·사용 기간에 따라 주의사항이 다릅니다.",
    ),
    (
        "외용 소염진통제로 사용",
        "먹는 약이 아닌 파스·겔·크림 등의 제형을 "
        "피부에 적용해 국소 통증·염증을 줄이는 "
        "용도를 뜻합니다.",
    ),
]

st.divider()
st.subheader("🔎 의약품 용어 쉽게 이해하기")
st.dataframe(
    pd.DataFrame(
        GLOSSARY,
        columns=["용어", "뜻"],
    ),
    hide_index=True,
    use_container_width=True,
    height=415,
)
st.caption(
    "용어 풀이와 성분 정보는 일반적인 참고자료이며, "
    "실제 사용은 제품 허가정보와 "
    "의료진 안내를 확인하세요."
)
