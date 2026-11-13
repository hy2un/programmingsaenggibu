"""동물 건강: 직사각형 모양의 네모를 수정함"""
from html import escape
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

st.markdown("""<style>
/* 동물 건강 페이지 디자인: 홈과 같은 부드러운 둥근 모서리 */
.stApp, [data-testid="stAppViewContainer"] {
    background: #fbfdfb !important;
}
h1, h2, h3 { color: #193d34 !important; letter-spacing: -.02em; }

/* 탭은 글자와 초록색 밑줄을 강조하고, 다른 UI의 둥근 모서리는 유지 */
.stTabs [data-baseweb="tab-list"] {
    display: flex;
    gap: 22px;
    background: transparent !important;
    border-bottom: 1px solid #d4e5da !important;
    padding: 0;
}
.stTabs [data-baseweb="tab"],
.stTabs button[role="tab"] {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 10px 3px 12px !important;
    color: #52685c !important;
    font-weight: 700 !important;
}
.stTabs button[role="tab"] *,
.stTabs [data-baseweb="tab"] * { color: inherit !important; }
.stTabs button[role="tab"][aria-selected="true"],
.stTabs button[role="tab"][aria-selected="true"] *,
.stTabs button[role="tab"]:hover,
.stTabs button[role="tab"]:hover * {
    color: #137f62 !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    background-color: #137f62 !important;
    height: 3px !important;
    border-radius: 0 !important;
}
.stTabs [data-baseweb="tab-border"] {
    background-color: #d4e5da !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: 14px; }

/* 반려동물 안내: 왼쪽 진한 세로선 없이, 홈과 동일한 둥근 연민트색 카드 */
.animal-safety-card {
    background: #eaf7ef;
    border: 1px solid #d5eadf;
    border-radius: 18px;
    box-shadow: none;
    padding: 18px 22px;
    margin: 12px 0 18px;
}
.animal-safety-card strong {
    display: block;
    color: #11654f;
    font-size: 1.02rem;
    margin-bottom: 5px;
}
.animal-safety-card p {
    margin: 0;
    color: #315749;
    font-size: .96rem;
    line-height: 1.65;
}

/* 기준 위치 찾기 · 주변 동물병원 검색 버튼: 초록색과 둥근 모서리 */
.stButton > button,
.stFormSubmitButton > button,
div[data-testid="stButton"] button,
div[data-testid="stFormSubmitButton"] button,
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-secondary"] {
    background: #147f62 !important;
    color: #ffffff !important;
    border: 1px solid #147f62 !important;
    border-radius: 14px !important;
    box-shadow: none !important;
    font-weight: 700 !important;
}
.stButton > button:hover,
.stFormSubmitButton > button:hover,
div[data-testid="stButton"] button:hover,
div[data-testid="stFormSubmitButton"] button:hover {
    background: #0d664e !important;
    color: #ffffff !important;
    border-color: #0d664e !important;
}
.stButton > button:focus-visible,
.stFormSubmitButton > button:focus-visible {
    outline: 2px solid #8dc9aa !important;
    outline-offset: 2px;
    box-shadow: none !important;
}

/* 지도 검색 폼: 연민트 배경과 둥근 모서리 유지 */
div[data-testid="stForm"] {
    background: #f3faf5;
    border: 1px solid #dcece2;
    border-radius: 16px !important;
    padding: 16px 18px;
}
.stTextInput input,
div[data-baseweb="select"] > div {
    background: #ffffff !important;
    border: 1px solid #cbded3 !important;
    border-radius: 12px !important;
}
.stTextInput input:focus {
    border-color: #137f62 !important;
    box-shadow: 0 0 0 1px #137f62 !important;
}
.stRadio input[type="radio"] { accent-color: #137f62 !important; }

/* 4개 분류 수치는 간결한 구분선으로 표시 */
div[data-testid="stMetric"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid #dcece2 !important;
    border-radius: 12px !important;
    padding: 5px 2px 10px;
    box-shadow: none !important;
}
div[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; }
div[data-testid="stAlert"] { border-radius: 15px !important; }
</style>
""", unsafe_allow_html=True)

ROOT = Path(__file__).resolve().parent.parent


def green_card(title, detail):
    """홈 화면처럼 부드럽게 둥근 연민트 안내 영역."""
    st.markdown(
        '<div class="animal-safety-card">'
        f'<strong>{escape(str(title))}</strong>'
        f'<p>{escape(str(detail))}</p>'
        '</div>',
        unsafe_allow_html=True,
    )


def load_animal_data():
    drug_path = ROOT / "animal_drug_data.csv"
    ingredient_path = ROOT / "animal_ingredient_data.csv"
    if not drug_path.exists() or not ingredient_path.exists():
        st.error("동물 약물 CSV가 없습니다. GitHub 최상위 폴더를 확인해 주세요.")
        st.stop()
    try:
        return (pd.read_csv(drug_path, encoding="utf-8-sig").fillna(""),
                pd.read_csv(ingredient_path, encoding="utf-8-sig").fillna(""))
    except (OSError, UnicodeError, pd.errors.ParserError) as err:
        st.error(f"동물 약 데이터 읽기 실패: {err}")
        st.stop()


def filter_rows(df, q, columns):
    if not q.strip():
        return df
    mask = df[columns].astype(str).apply(
        lambda s: s.str.contains(q.strip(), case=False, regex=False, na=False)
    ).any(axis=1)
    return df[mask]


def kakao_key():
    try:
        return st.secrets.get("KAKAO_REST_API_KEY", "")
    except (KeyError, FileNotFoundError):
        return ""


def kakao_search(endpoint, params, key):
    url = f"https://dapi.kakao.com/v2/local/search/{endpoint}.json"
    response = requests.get(url, params=params,
        headers={"Authorization": f"KakaoAK {key}"}, timeout=12)
    response.raise_for_status()
    return response.json()


def locate(query, key):
    """주소 API를 먼저 조회하고, 결과가 없으면 장소명 키워드 API로 찾는다."""
    items = kakao_search("address", {"query": query}, key).get("documents", [])
    candidates = []
    for item in items[:8]:
        candidates.append({"label": item.get("address_name") or query,
            "lon": float(item["x"]), "lat": float(item["y"])})
    if not candidates:
        items = kakao_search("keyword", {"query": query, "size": 15}, key).get("documents", [])
        for item in items:
            candidates.append({"label": f'{item.get("place_name", "")} — {item.get("road_address_name") or item.get("address_name", "")}',
                "lon": float(item["x"]), "lat": float(item["y"])})
    return candidates


def nearby_vets(lon, lat, radius_km, key):
    """카카오 키워드 검색 결과에서 동물병원만 추출한다."""
    found = {}
    for page in range(1, 4):
        answer = kakao_search("keyword", {"query": "동물병원", "x": lon, "y": lat,
                               "radius": int(radius_km * 1000), "sort": "distance",
                               "size": 15, "page": page}, key)
        for p in answer.get("documents", []):
            info = p.get("place_name", "") + " " + p.get("category_name", "")
            if "동물병원" not in info and "수의" not in info:
                continue
            found[p.get("id") or p.get("place_name")] = p
        if answer.get("meta", {}).get("is_end", True):
            break
    return sorted(found.values(), key=lambda x: int(x.get("distance") or 0))


def pin(color):
    # 내장 SVG 데이터 URI: 별도 이미지 파일을 만들지 않는 작은 지도 핀
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="36" height="48" viewBox="0 0 36 48">'
           f'<path d="M18 2C9 2 2 9 2 18c0 12 16 28 16 28s16-16 16-28C34 9 27 2 18 2Z" fill="{color}" stroke="white" stroke-width="2"/>'
           '<circle cx="18" cy="18" r="7" fill="white"/></svg>')
    return {"url": "data:image/svg+xml;charset=utf-8," + quote(svg),
            "width": 36, "height": 48, "anchorX": 18, "anchorY": 48}


def show_map(df, center):
    points = df[["이름", "lat", "lon"]].copy()
    points["icon"] = [pin("#ea5455") for _ in range(len(points))]
    base = pd.DataFrame([{"이름": "검색 기준 위치", "lat": center["lat"],
                          "lon": center["lon"], "icon": pin("#147f66")}])
    all_points = pd.concat([points, base], ignore_index=True)
    deck = pdk.Deck(
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        initial_view_state=pdk.ViewState(latitude=center["lat"], longitude=center["lon"], zoom=13, pitch=0),
        layers=[
            pdk.Layer("IconLayer", all_points, get_icon="icon", get_position="[lon, lat]",
                      get_size=22, size_scale=1, pickable=True),
        ],
        tooltip={"text": "{이름}"},
    )
    st.pydeck_chart(deck, use_container_width=True)
    st.caption("초록색 핀: 검색 기준 위치 / 빨간색 핀: 동물병원. 핀 크기는 검색 반경과 무관합니다.")


st.title("🐾 동물 건강")
st.caption("반려동물 약물과 성분, 동물종별 주의 약물, 동물병원 위치를 확인하세요.")
green_card("💚 반려동물 약물 안전 안내", "사람용 약을 반려동물에게 임의로 투여하지 마세요. 약물을 먹었거나 피부에 노출됐다면 수의사에게 즉시 문의하세요.")

animal_drugs, animal_ingredients = load_animal_data()
tab_drug, tab_ing, tab_risk, tab_vet = st.tabs([
    "💊 동물 약", "🧪 동물 약 성분", "⚠️ 강아지·고양이 주의 약물", "📍 동물병원 위치",
])

with tab_drug:
    st.subheader("동물 약 찾아보기")

    # 원본 CSV는 대상동물을 확정하지 않은 제제가 많다.
    # '수의사 판단'을 다른 동물 전용이나 투여 금지로 해석하지 않는다.
    species_text = animal_drugs["대상동물"].astype(str)
    dog_mask = species_text.str.contains("개", regex=False)
    cat_mask = species_text.str.contains("고양이", regex=False)
    unconfirmed_mask = ~(dog_mask | cat_mask)
    dog_only = int((dog_mask & ~cat_mask).sum())
    cat_only = int((~dog_mask & cat_mask).sum())
    both = int((dog_mask & cat_mask).sum())
    unconfirmed = int(unconfirmed_mask.sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("강아지만 명시", dog_only)
    c2.metric("고양이만 명시", cat_only)
    c3.metric("두 동물 모두 명시", both)
    c4.metric("대상 동물 미확정", unconfirmed)

    green_card("🐶 🐱 동물별 분류 안내", "대상 동물 미확정은 현재 자료에 수의사 판단으로 표시된 제제입니다. 다른 동물 전용이라는 뜻은 아니며 제품 허가정보와 수의사 확인이 필요합니다.")

    species = st.radio(
        "대상 동물 구분",
        ["전체", "강아지", "고양이", "대상 동물 미확정"],
        horizontal=True,
        key="animal_drug_species",
    )
    q = st.text_input("동물 약·성분 검색", placeholder="예: 플루랄라너, 외부기생충", key="animal_drug_q")
    category = st.selectbox("동물 약 종류", ["전체 보기"] + sorted(animal_drugs["분류"].astype(str).unique()), key="animal_drug_cat")
    result = animal_drugs.copy()
    if species == "강아지":
        result = result.loc[dog_mask].copy()
    elif species == "고양이":
        result = result.loc[cat_mask].copy()
    elif species == "대상 동물 미확정":
        result = result.loc[unconfirmed_mask].copy()
    if category != "전체 보기":
        result = result[result["분류"] == category]
    result = filter_rows(result, q, ["약물명", "분류", "주요성분", "사용영역"])
    st.write(f"검색 결과: **{len(result)}개** / 전체 {len(animal_drugs)}개")
    if result.empty:
        st.info("해당 조건의 동물 약 정보가 없습니다.")
    else:
        st.dataframe(result[["약물명", "분류", "주요성분", "대상동물", "사용영역"]],
                     hide_index=True, use_container_width=True, height=310)
        idx = st.selectbox("자세히 볼 약물 선택", result.index.tolist(),
                           format_func=lambda i: str(result.loc[i, "약물명"]), key="animal_drug_detail")
        item = result.loc[idx]
        st.write(f"**약물:** {item['약물명']} / **대상 동물:** {item['대상동물']}")
        st.write(f"**사용 영역:** {item['사용영역']}")
        green_card("🌿 약물 사용 시 주의사항", item["주의사항"])
        if "데이터형태" in result.columns:
            st.caption(f"데이터 구분: {item['데이터형태']}")

with tab_ing:
    st.subheader("동물 약 성분 사전")
    q = st.text_input("성분명·영문명·설명 검색", placeholder="예: Fluralaner", key="animal_ingredient_q")
    result = filter_rows(animal_ingredients.copy(), q, ["성분명", "영문명", "분류", "설명"])
    st.write(f"조회된 성분 **{len(result)}개 / 전체 {len(animal_ingredients)}개**")
    if result.empty:
        st.info("성분 검색 결과가 없습니다.")
    else:
        st.dataframe(result, hide_index=True, use_container_width=True, height=300)
        idx = st.selectbox("자세히 볼 성분 선택", result.index.tolist(),
                           format_func=lambda i: str(result.loc[i, "성분명"]), key="animal_ingredient_detail")
        row = result.loc[idx]
        st.write(f"**{row['성분명']} ({row['영문명']})** — {row['설명']}")
        green_card("🌿 해당 성분의 주의사항", row["주의사항"])

# 수의학 자료에 근거한 대표적 위험 노출 사례. 이 목록은 전체 금기 목록이 아니다.
DOG_RISKS = [
    ("이부프로펜·나프록센 등 사람용 NSAIDs", "임의 투여 금지", "위장관 궤양·급성 신손상 위험", "https://www.petpoisonhelpline.com/poison/nsaids/"),
    ("아세트아미노펜", "임의 투여 금지", "과량 노출 시 간·혈액 손상 위험", "https://www.aspca.org/news/protect-your-pet-top-5-toxic-dangers-your-home"),
    ("자일리톨 함유 의약품·간식", "특히 주의", "개에게 저혈당·간 손상 위험", "https://www.aspca.org/news/updated-safety-warning-xylitol-how-protect-your-pets"),
    ("슈도에페드린 등 감기약 성분", "임의 투여 금지", "심혈관·신경계 이상반응 가능", "https://www.aspca.org/news/can-human-allergy-medication-be-harmful-pets-our-experts-explain"),
]
CAT_RISKS = [
    ("아세트아미노펜", "매우 위험", "소량 노출에도 심한 중독 발생 가능", "https://vcahospitals.com/know-your-pet/household-hazards-toxic-hazards-for-cats"),
    ("이부프로펜·나프록센 등 NSAIDs", "임의 투여 금지", "위장관·신장 손상 위험", "https://www.petpoisonhelpline.com/poison/nsaids/"),
    ("강아지용 퍼메트린 구충제", "고양이 사용 금지", "피부 노출 및 그루밍으로도 신경계 중독 위험", "https://vcahospitals.com/know-your-pet/household-hazards-toxic-hazards-for-cats"),
    ("미녹시딜 외용제", "접촉·섭취 주의", "고양이에서 심장·호흡기계 이상 발생 가능", "https://vcahospitals.com/know-your-pet/household-hazards-toxic-hazards-for-cats"),
    ("아스피린", "수의사 관리 필요", "고양이에서 대사·중독 위험이 커 임의 투여 금지", "https://www.aspca.org/news/not-all-pets-are-same-why-species-matters-pet-toxins"),
]
with tab_risk:
    st.subheader("동물종별 주의해야 할 약물과 제품")
    species = st.radio("동물종 선택", ["강아지", "고양이"], horizontal=True, key="risk_species")
    info = DOG_RISKS if species == "강아지" else CAT_RISKS
    table = pd.DataFrame(info, columns=["성분·제품", "구분", "주의 이유", "근거 자료"])
    st.dataframe(table, hide_index=True, use_container_width=True,
                 column_config={"근거 자료": st.column_config.LinkColumn("수의학 근거")})
    green_card("🌿 위험 약물 목록 안내", "대표 위험 사례만 정리했습니다. 목록에 없는 약도 위험할 수 있으며 실제 투약·응급조치는 수의사가 판단합니다.")
    st.warning("의심되는 약물을 먹었거나 피부에 닿았다면 즉시 동물병원에 연락하세요. 임의로 구토를 유도하지 마세요.")

with tab_vet:
    st.subheader("근처 동물병원 찾기")
    green_card("📍 위치 검색 방법", "주소·장소명을 입력한 뒤 후보에서 기준 위치를 선택하세요. 반경은 직선거리이며 실제 이동거리가 아닙니다.")
    key = kakao_key()
    if not key:
        st.error("Streamlit Secrets에 KAKAO_REST_API_KEY를 등록해 주세요.")
    else:
        with st.form("vet_location_form"):
            query = st.text_input(
                "검색 기준 위치",
                placeholder="예: 서울시청, 서울특별시 중구 세종대로 110",
                key="vet_query",
            )
            st.caption("장소명 예시: 국회의사당 · 서울중앙지방법원 · 서울대학교")
            radius_km = st.selectbox("검색 반경 (km)", [1, 2, 3, 5, 10], index=2, key="vet_radius")
            st.caption(f"반경 {radius_km}km는 기준 위치에서 직선거리 {radius_km * 1000:,}m 이내입니다. 이동거리가 아닙니다.")
            submit = st.form_submit_button("기준 위치 찾기", type="primary")
        if submit:
            if not query.strip():
                st.warning("주소 또는 장소명을 입력해 주세요.")
            else:
                try:
                    candidates = locate(query.strip(), key)
                    st.session_state["vet_candidates"] = candidates
                    st.session_state["vet_radius_choice"] = radius_km
                    st.session_state.pop("vet_results_1103", None)
                    if not candidates:
                        st.warning("해당 위치를 찾지 못했습니다. 주소·장소명을 변경해 보세요.")
                except (requests.RequestException, ValueError, KeyError) as err:
                    st.error(f"위치 검색 오류: {type(err).__name__}")
        candidates = st.session_state.get("vet_candidates", [])
        if candidates:
            sel = st.selectbox("기준 위치 선택", range(len(candidates)),
                format_func=lambda i: f"{i+1}. {candidates[i]['label']}", key="vet_location_sel")
            if st.button("이 위치 주변 동물병원 검색", type="primary", key="vet_search_btn"):
                place = candidates[sel]
                try:
                    raw = nearby_vets(place["lon"], place["lat"],
                                       st.session_state.get("vet_radius_choice", 3), key)
                    st.session_state["vet_center_1103"] = place
                    st.session_state["vet_results_1103"] = [{
                        "이름": p.get("place_name", ""), "거리(m)": int(p.get("distance") or 0),
                        "전화": p.get("phone", ""),
                        "주소": p.get("road_address_name") or p.get("address_name", ""),
                        "상세정보": p.get("place_url", ""),
                        "lat": float(p["y"]), "lon": float(p["x"]),
                    } for p in raw]
                except (requests.RequestException, ValueError, KeyError) as err:
                    st.error(f"동물병원 검색 오류: {type(err).__name__}")
        rows = st.session_state.get("vet_results_1103")
        if rows is not None:
            if not rows:
                st.info("선택한 반경에서 동물병원을 찾지 못했습니다.")
            else:
                df = pd.DataFrame(rows)
                st.success(f"동물병원 {len(df)}곳을 찾았습니다.")
                if len(df) >= 45:
                    st.caption("최대 45곳까지 조회합니다. 다른 결과가 더 있을 수 있습니다.")
                st.dataframe(df[["이름", "거리(m)", "전화", "주소", "상세정보"]],
                    hide_index=True, use_container_width=True, height=330,
                    column_config={"상세정보": st.column_config.LinkColumn("카카오맵 열기")})
                show_map(df, st.session_state["vet_center_1103"])
