"""약 종류: 제품 136개·성분 257개·주의사항 178개 검색."""
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st

from drug_data_tools import load_data

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
 background:#137f62 !important;
 height:3px !important;border-radius:3px !important;
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
div[data-testid="stMetric"] {
 background:#f2faf5;border:1px solid #dcece3;
 border-radius:16px;padding:10px 14px;
}
</style>""", unsafe_allow_html=True)

ROOT = Path(__file__).resolve().parent.parent


def info_search(name):
    """성분·제품 이름의 정보 검색 링크 생성."""
    return (
        "https://www.google.com/search?q="
        + quote(f'site:health.kr "{name}"')
    )


def add_sources(frame, name_col):
    frame = frame.copy().fillna("")
    existing = frame.get(
        "출처URL",
        pd.Series("", index=frame.index),
    ).astype(str).str.strip()

    frame["기존 제품 링크"] = existing.where(
        existing.str.contains(
            "/drug/", regex=False
        ),
        "",
    )
    frame["정보 검색"] = (
        frame[name_col]
        .astype(str)
        .map(info_search)
    )
    frame["출처 상태"] = existing.map(
        lambda value: (
            "기존 제품 링크·연결 확인 필요"
            if "/drug/" in value
            else "개별 출처 검증 필요"
        )
    )
    return frame


def filter_text(df, query, cols):
    if not query.strip():
        return df
    mask = df[cols].astype(str).apply(
        lambda s: s.str.contains(
            query.strip(),
            case=False,
            regex=False,
            na=False,
        )
    ).any(axis=1)
    return df[mask]


st.title("🗂️ 약 종류")
st.caption(
    "등록 의약품, 의약품 성분, "
    "성분별 주의사항을 검색할 수 있습니다."
)

try:
    drugs, ingredients = load_data()
except (
    FileNotFoundError,
    KeyError,
    ValueError,
    pd.errors.ParserError,
) as err:
    st.error(
        f"의약품·성분 데이터를 확인해 주세요: {err}"
    )
    st.stop()

# 확장 약물 카탈로그 불러오기
extra_path = ROOT / "drug_catalog_extra.csv"

if extra_path.exists():
    try:
        extra = pd.read_csv(
            extra_path,
            encoding="utf-8-sig",
        ).fillna("")
        required = {
            "성분명", "약물분류", "설명", "주의사항"
        }
        missing = required - set(extra.columns)

        if missing:
            st.error(
                "drug_catalog_extra.csv 열 이름 확인: "
                + ", ".join(sorted(missing))
            )
            st.stop()

    except (
        OSError,
        UnicodeError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
    ) as err:
        st.error(
            f"카탈로그 CSV를 읽을 수 없습니다: {err}"
        )
        st.stop()
else:
    extra = pd.DataFrame(
        columns=[
            "성분명", "약물분류", "설명", "주의사항"
        ]
    )

c1, c2, c3 = st.columns(3)
c1.metric("등록 의약품", len(drugs))
c2.metric("성분 사전", len(ingredients))
c3.metric(
    "제품 분류",
    drugs["카테고리"].nunique(),
)

product_tab, ingredient_tab, caution_tab = st.tabs([
    f"💊 의약품 전체 ({len(drugs)})",
    f"🧪 성분 전체 ({len(ingredients)})",
    f"⚠️ 성분별 주의사항 ({len(extra)})",
])

# 의약품 제품 조회
with product_tab:
    st.subheader("의약품 제품 전체 보기")

    category = st.selectbox(
        "제품 분류 선택",
        ["전체 보기"] + sorted(
            drugs["카테고리"].dropna().unique()
        ),
        key="all_drug_cat",
    )
    query = st.text_input(
        "제품명·제조사·성분 검색",
        placeholder=(
            "검색하지 않으면 전체 목록을 표시합니다."
        ),
        key="all_drug_query",
    )

    filtered = (
        drugs
        if category == "전체 보기"
        else drugs[drugs["카테고리"] == category]
    )

    filtered = filter_text(
        filtered.copy(),
        query,
        ["제품명", "제조사", "카테고리", "성분"],
    )

    st.write(
        f"조회된 제품 **{len(filtered)}개 / "
        f"전체 {len(drugs)}개**"
    )

    if filtered.empty:
        st.info(
            "검색 조건에 해당하는 의약품이 없습니다. "
            "검색어 또는 분류를 변경해 주세요."
        )
    else:
        view = add_sources(filtered, "제품명")
        cols = [
            "제품명",
            "제조사",
            "카테고리",
            "성분",
        ]
        if "전문일반구분" in view.columns:
            cols.append("전문일반구분")

        cols += [
            "기존 제품 링크",
            "정보 검색",
            "출처 상태",
        ]

        st.dataframe(
            view[cols],
            hide_index=True,
            use_container_width=True,
            height=450,
            column_config={
                "기존 제품 링크": (
                    st.column_config.LinkColumn(
                        "기존 제품 링크"
                    )
                ),
                "정보 검색": (
                    st.column_config.LinkColumn(
                        "제품별 검색"
                    )
                ),
            },
        )

# 성분 전체 조회
with ingredient_tab:
    st.subheader("의약품 성분 전체 보기")

    category = st.selectbox(
        "성분 분류 선택",
        ["전체 보기"] + sorted(
            ingredients["분류"].dropna().unique()
        ),
        key="all_ingredient_cat",
    )
    query = st.text_input(
        "성분명·분류·설명 검색",
        placeholder="예: 항히스타민, 진해, 아세트아미노펜",
        key="all_ingredient_query",
    )

    filtered = (
        ingredients
        if category == "전체 보기"
        else ingredients[
            ingredients["분류"] == category
        ]
    )
    filtered = filter_text(
        filtered.copy(),
        query,
        ["성분명", "분류", "설명"],
    )

    st.write(
        f"조회된 성분 **{len(filtered)}개 / "
        f"전체 {len(ingredients)}개**"
    )

    if filtered.empty:
        st.info(
            "검색 조건에 해당하는 성분이 없습니다. "
            "검색어 또는 분류를 변경해 주세요."
        )
    else:
        view = add_sources(filtered, "성분명")
        st.dataframe(
            view[
                [
                    "성분명",
                    "분류",
                    "설명",
                    "기존 제품 링크",
                    "정보 검색",
                    "출처 상태",
                ]
            ],
            hide_index=True,
            use_container_width=True,
            height=450,
            column_config={
                "기존 제품 링크": (
                    st.column_config.LinkColumn(
                        "기존 제품 링크"
                    )
                ),
                "정보 검색": (
                    st.column_config.LinkColumn(
                        "성분별 검색"
                    )
                ),
            },
        )

    st.caption(
        "의약품 용어 13개의 뜻은 왼쪽 "
        "'성분 사전' 페이지 하단에서 확인할 수 있습니다."
    )

# 확장 카탈로그: 성분별 주의사항
with caution_tab:
    st.subheader("성분별 약물 분류와 주의사항")

    st.info(
        "이곳의 178개는 새로운 제품 178개가 아닙니다. "
        "성분 사전 257개와 중복되는 성분에 "
        "주의사항을 보완한 자료입니다."
    )

    if extra.empty:
        st.warning(
            "drug_catalog_extra.csv 파일이 없습니다. "
            "GitHub 최상위 폴더에 업로드해 주세요."
        )
    else:
        category = st.selectbox(
            "약물 분류 선택",
            ["전체 보기"] + sorted(
                extra["약물분류"].dropna().unique()
            ),
            key="all_caution_cat",
        )
        query = st.text_input(
            "성분명·약물분류·설명·주의사항 검색",
            key="all_caution_query",
        )

        filtered = (
            extra
            if category == "전체 보기"
            else extra[extra["약물분류"] == category]
        )
        filtered = filter_text(
            filtered.copy(),
            query,
            ["성분명", "약물분류", "설명", "주의사항"],
        )

        st.write(
            f"조회된 주의사항 **{len(filtered)}개 / "
            f"전체 {len(extra)}개**"
        )

        if filtered.empty:
            st.info(
                "검색 조건에 해당하는 약물 정보가 없습니다. "
                "검색어나 분류를 변경해 주세요."
            )
        else:
            view = filtered.copy()
            view["추가 정보 검색"] = (
                view["성분명"]
                .astype(str)
                .map(info_search)
            )

            st.dataframe(
                view[
                    [
                        "성분명",
                        "약물분류",
                        "설명",
                        "주의사항",
                        "추가 정보 검색",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
                height=450,
                column_config={
                    "추가 정보 검색": (
                        st.column_config.LinkColumn(
                            "성분별 검색"
                        )
                    )
                },
            )

st.caption(
    "정보 검색 링크는 해당 항목명을 웹에서 찾는 경로이며 "
    "개별 원문 출처가 검증됐다는 뜻은 아닙니다. "
    "제품 허가·투여 관련 정보는 공식 원문을 확인하세요."
)
