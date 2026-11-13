"""사람 병원·약국: 주소·건물명 검색, 반경 km, 작은 지도 핀."""
from urllib.parse import quote

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

# 페이지별 민트색 디자인
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
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
 background:#137f62 !important;
 border-color:#137f62 !important;color:white !important;
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
 background:#0f6b53 !important;
 border-color:#0f6b53 !important;
}
.stTextInput input,div[data-baseweb="select"] > div {
 border-radius:13px !important;
}
div[data-testid="stDataFrame"] {border-radius:14px;overflow:hidden;}
div[data-testid="stAlert"] {border-radius:17px !important;}
div[data-testid="stForm"] {
 background:#f2faf5;border:1px solid #d7ebe0;
 border-radius:18px;padding:18px;
}
.stFormSubmitButton > button {
 background:#137f62 !important;
 border-color:#137f62 !important;
 color:white !important;
}
</style>""", unsafe_allow_html=True)

st.title("📍 근처 병원·약국")
st.caption(
    "주소 또는 건물·장소명을 검색한 뒤 "
    "기준 위치를 선택하세요."
)


def kakao_key():
    try:
        return st.secrets.get("KAKAO_REST_API_KEY", "")
    except (KeyError, FileNotFoundError):
        return ""


def kakao_search(endpoint, params, key):
    url = (
        "https://dapi.kakao.com/v2/local/search/"
        f"{endpoint}.json"
    )
    response = requests.get(
        url,
        params=params,
        headers={"Authorization": f"KakaoAK {key}"},
        timeout=12,
    )
    response.raise_for_status()
    return response.json()


def locate(query, key):
    """주소 API 우선 검색, 결과가 없으면 장소명 검색."""
    items = kakao_search(
        "address", {"query": query}, key
    ).get("documents", [])

    candidates = []
    for item in items[:8]:
        candidates.append({
            "label": item.get("address_name") or query,
            "lon": float(item["x"]),
            "lat": float(item["y"]),
        })

    if not candidates:
        items = kakao_search(
            "keyword",
            {"query": query, "size": 15},
            key,
        ).get("documents", [])

        for item in items:
            name = item.get("place_name", "")
            address = (
                item.get("road_address_name")
                or item.get("address_name", "")
            )
            candidates.append({
                "label": f"{name} — {address}",
                "lon": float(item["x"]),
                "lat": float(item["y"]),
            })

    return candidates


def is_vet(item):
    info = (
        item.get("place_name", "")
        + " "
        + item.get("category_name", "")
    )
    return any(
        word in info
        for word in ["동물병원", "수의", "동물의료"]
    )


def nearby(lon, lat, kind, radius_km, key):
    """동물병원과 사람 병원·약국을 분리하여 검색."""
    category = "HP8" if kind == "병원·의원" else "PM9"
    found = {}

    for page in range(1, 4):
        answer = kakao_search(
            "category",
            {
                "category_group_code": category,
                "x": lon,
                "y": lat,
                "radius": int(radius_km * 1000),
                "sort": "distance",
                "size": 15,
                "page": page,
            },
            key,
        )

        for place in answer.get("documents", []):
            if kind == "병원·의원" and is_vet(place):
                continue
            found[
                place.get("id") or place.get("place_name")
            ] = place

        if answer.get("meta", {}).get("is_end", True):
            break

    return sorted(
        found.values(),
        key=lambda item: int(
            item.get("distance") or 0
        ),
    )


def pin(color):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="36" height="48" viewBox="0 0 36 48">'
        '<path d="M18 2C9 2 2 9 2 18'
        'c0 12 16 28 16 28s16-16 16-28'
        f'C34 9 27 2 18 2Z" fill="{color}" '
        'stroke="white" stroke-width="2"/>'
        '<circle cx="18" cy="18" r="7" fill="white"/>'
        '</svg>'
    )
    return {
        "url": "data:image/svg+xml;charset=utf-8," + quote(svg),
        "width": 36,
        "height": 48,
        "anchorX": 18,
        "anchorY": 48,
    }


def show_map(df, center):
    points = df[["이름", "lat", "lon"]].copy()
    points["icon"] = [
        pin("#ea5455") for _ in range(len(points))
    ]
    base = pd.DataFrame([{
        "이름": "검색 기준 위치",
        "lat": center["lat"],
        "lon": center["lon"],
        "icon": pin("#147f66"),
    }])
    all_points = pd.concat(
        [points, base],
        ignore_index=True,
    )

    deck = pdk.Deck(
        map_style=(
            "https://basemaps.cartocdn.com/"
            "gl/positron-gl-style/style.json"
        ),
        initial_view_state=pdk.ViewState(
            latitude=center["lat"],
            longitude=center["lon"],
            zoom=13,
            pitch=0,
        ),
        layers=[
            pdk.Layer(
                "IconLayer",
                all_points,
                get_icon="icon",
                get_position="[lon, lat]",
                get_size=22,
                size_scale=1,
                pickable=True,
            ),
        ],
        tooltip={"text": "{이름}"},
    )

    st.pydeck_chart(
        deck,
        use_container_width=True,
    )
    st.caption(
        "초록색 핀: 검색 기준 위치 / "
        "빨간색 핀: 의료기관. "
        "핀 크기는 검색 반경과 무관합니다."
    )


key = kakao_key()

if not key:
    st.error(
        "Streamlit Secrets에 KAKAO_REST_API_KEY를 "
        "등록해야 합니다."
    )
    st.stop()

with st.form("human_search_form"):
    query = st.text_input(
        "검색 기준 위치",
        placeholder=(
            "예: 서울시청, 서울특별시 중구 세종대로 110"
        ),
    )
    st.caption(
        "장소명 예시: 국회의사당 · "
        "서울중앙지방법원 · 서울대학교"
    )
    kind = st.radio(
        "찾을 장소",
        ["병원·의원", "약국"],
        horizontal=True,
    )
    radius_km = st.selectbox(
        "검색 반경 (km)",
        [1, 2, 3, 5, 10],
        index=2,
    )
    st.caption(
        f"반경 {radius_km}km는 기준 위치에서 "
        f"직선거리 {radius_km * 1000:,}m 이내입니다. "
        "운전·도보 이동거리가 아닙니다."
    )
    locate_submit = st.form_submit_button(
        "기준 위치 찾기",
        type="primary",
    )

if locate_submit:
    if not query.strip():
        st.warning("주소 또는 건물명을 입력해 주세요.")
    else:
        try:
            candidates = locate(query.strip(), key)
            st.session_state["human_candidates"] = candidates
            st.session_state["human_kind"] = kind
            st.session_state["human_radius"] = radius_km
            st.session_state.pop("human_results", None)

            if not candidates:
                st.warning(
                    "검색 위치를 찾지 못했습니다. "
                    "정확한 주소나 장소명으로 다시 검색해 주세요."
                )
        except (
            requests.RequestException,
            ValueError,
            KeyError,
        ) as err:
            st.error(
                f"기준 위치 검색 중 오류: {type(err).__name__}"
            )

candidates = st.session_state.get(
    "human_candidates", []
)

if candidates:
    labels = [
        f"{i+1}. {candidate['label']}"
        for i, candidate in enumerate(candidates)
    ]
    selection = st.selectbox(
        "검색할 정확한 위치 선택",
        list(range(len(labels))),
        format_func=lambda i: labels[i],
    )

    if st.button(
        "이 위치 주변 검색",
        type="primary",
    ):
        place = candidates[selection]
        try:
            found = nearby(
                place["lon"],
                place["lat"],
                st.session_state.get(
                    "human_kind", "병원·의원"
                ),
                st.session_state.get(
                    "human_radius", 3
                ),
                key,
            )

            st.session_state["human_center"] = place
            st.session_state["human_results"] = [
                {
                    "이름": p.get("place_name", ""),
                    "거리(m)": int(
                        p.get("distance") or 0
                    ),
                    "전화": p.get("phone", ""),
                    "주소": (
                        p.get("road_address_name")
                        or p.get("address_name", "")
                    ),
                    "상세정보": p.get("place_url", ""),
                    "lat": float(p["y"]),
                    "lon": float(p["x"]),
                }
                for p in found
            ]
        except (
            requests.RequestException,
            ValueError,
            KeyError,
        ) as err:
            st.error(
                f"주변 장소 검색 중 오류: {type(err).__name__}"
            )

rows = st.session_state.get("human_results")

if rows is not None:
    if not rows:
        st.info(
            "선택한 반경에 결과가 없습니다. "
            "위치·검색 범위를 바꿔 주세요."
        )
    else:
        df = pd.DataFrame(rows)
        st.success(f"{len(df)}곳을 찾았습니다.")

        if len(df) >= 45:
            st.caption(
                "최대 45곳까지 조회합니다. "
                "검색 결과가 더 있을 수 있습니다."
            )

        st.dataframe(
            df[
                ["이름", "거리(m)", "전화", "주소", "상세정보"]
            ],
            hide_index=True,
            use_container_width=True,
            height=330,
            column_config={
                "상세정보": st.column_config.LinkColumn(
                    "카카오맵 열기"
                )
            },
        )
        show_map(
            df,
            st.session_state["human_center"],
        )
