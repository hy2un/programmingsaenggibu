"""My MediCare 나의 건강 기록: 등록·수정·분석·타임라인·PDF."""

import io
import json
from datetime import date
from html import escape

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from drug_data_tools import (
    load_data, load_condition_data,
    get_selected_drugs, find_duplicates,
)

from medical_data import (
    MedicalStoreError, cloud_ready, get_record,
    init_record, refresh_record, is_logged_in,
    login_configured, normalize_record,
    save_with_message, delete_all,
)


# ================================================
# 페이지 디자인
# ================================================

st.markdown("""<style>
.stApp {background:#fbfdfc;}
[data-testid="stSidebar"] {
    background:#eef5f0 !important;
}
h1,h2,h3 {
    color:#193d34 !important;
    letter-spacing:-.025em;
}
.stTabs [data-baseweb="tab-highlight"] {
    background:#137f62 !important;
}
.stTabs [data-baseweb="tab"] {
    font-weight:700;
}
.stButton > button,
.stFormSubmitButton > button {
    border-radius:13px !important;
}
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background:#137f62 !important;
    border-color:#137f62 !important;
    color:white !important;
}
div[data-testid="stDataFrame"] {
    border-radius:14px;
    overflow:hidden;
}
</style>""", unsafe_allow_html=True)


st.title("🩺 나의 건강 기록")
st.caption(
    "내가 직접 입력한 정보를 저장하고, "
    "복용 약물과 건강 변화를 한곳에서 확인합니다."
)


# ================================================
# Google 로그인과 Supabase 연결 확인
# ================================================

if login_configured() and not is_logged_in():
    st.info(
        "개인 기록을 확인하려면 "
        "Google 계정으로 로그인해 주세요."
    )
    if st.button(
        "Google 계정으로 로그인",
        type="primary",
    ):
        st.login()
    st.stop()


try:
    init_record()
except MedicalStoreError as exc:
    st.error(str(exc))
    st.stop()


# Google 이메일은 화면에 표시하지 않고
# Supabase의 email 컬럼에만 저장합니다.

if is_logged_in():
    if not cloud_ready():
        st.error(
            "Google 로그인은 완료됐지만 "
            "Supabase가 연결되지 않았습니다. "
            "Streamlit Secrets의 SUPABASE_URL과 "
            "SUPABASE_SECRET_KEY를 확인하세요. "
            "연결 전에는 영구 저장을 사용할 수 없습니다."
        )
        if st.button(
            "로그아웃",
            key="record_logout_unconnected",
        ):
            st.logout()
        st.stop()

    st.caption(
        "🔒 클라우드 기록 연결됨 · "
        "계정별 저장 (새 탭에서도 불러오기 가능)"
    )

    c1, c2 = st.columns([1, 1])

    if c1.button(
        "서버의 최신 기록 불러오기",
        key="record_refresh",
    ):
        try:
            refresh_record()
            st.rerun()
        except MedicalStoreError as exc:
            st.error(str(exc))

    if c2.button(
        "로그아웃",
        key="record_logout",
    ):
        st.logout()

else:
    st.caption(
        "가상 기록 시연 모드 · "
        "이 세션에서만 유지되며 영구 저장되지 않습니다."
    )


# ================================================
# 의약품·질환 데이터 불러오기
# ================================================

try:
    drug_df, ingredient_df = load_data()
    condition_df = load_condition_data()

except (
    OSError, KeyError, ValueError,
    pd.errors.ParserError,
) as exc:
    st.error(
        f"의약품·질환 데이터를 확인해 주세요: {exc}"
    )
    st.stop()


# ================================================
# 저장 및 데이터 편집 공통 함수
# ================================================

def apply_change(updated):
    if save_with_message(updated):
        st.rerun()


def cleaned_rows(frame, fields):
    result = []

    for row in frame.to_dict("records"):
        item = {}

        for field in fields:
            value = row.get(field, "")
            item[field] = (
                ""
                if pd.isna(value)
                else value
            )

        if any(
            str(value).strip()
            for value in item.values()
        ):
            result.append(item)

    return result


# ================================================
# 진료 요약 PDF 생성
# ================================================

def pdf_summary(record, include):
    """진료 참고용 PDF. 내장 CID 한글 글꼴 사용."""

    pdfmetrics.registerFont(
        UnicodeCIDFont("HYGothic-Medium")
    )

    normal = ParagraphStyle(
        "med_normal",
        fontName="HYGothic-Medium",
        fontSize=10,
        leading=17,
        textColor=colors.HexColor("#233b33"),
        alignment=TA_LEFT,
        spaceAfter=6,
        wordWrap="CJK",
    )

    heading = ParagraphStyle(
        "med_heading",
        parent=normal,
        fontSize=14,
        leading=22,
        textColor=colors.HexColor("#137f62"),
        spaceBefore=14,
    )

    title = ParagraphStyle(
        "med_title",
        parent=normal,
        fontSize=20,
        leading=29,
        spaceAfter=15,
    )

    output = io.BytesIO()

    pdf = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm,
    )

    parts = [
        Paragraph(
            "My MediCare | 진료 준비 요약서",
            title,
        ),
        Paragraph(
            f"작성일: {date.today().isoformat()} "
            "/ 사용자 입력 정보",
            normal,
        ),
        Paragraph(
            "의료진 상담용 참고자료이며 "
            "진단서·처방전이 아닙니다.",
            normal,
        ),
        Spacer(1, 8),
    ]

    def section(label, items):
        parts.append(
            Paragraph(escape(label), heading)
        )

        for item in (items or ["기록 없음"]):
            parts.append(
                Paragraph(
                    "- " + escape(str(item)),
                    normal,
                )
            )

    if include["drugs"]:
        section(
            "현재 등록된 복용 약물",
            record["drugs"],
        )

    if include["conditions"]:
        section(
            "등록된 질환·증상",
            record["conditions"],
        )

    if include["allergies"]:
        section(
            "알레르기",
            [
                f"{x['name']} — {x['reaction']}"
                for x in record["allergies"]
            ],
        )

    if include["timeline"]:
        rows = sorted(
            record["timeline"],
            key=lambda x: x["date"],
            reverse=True,
        )[:15]

        section(
            "최근 건강 변화",
            [
                f"{x['date']} / {x['kind']} / "
                f"{x['title']} / {x['severity']}/10"
                for x in rows
            ],
        )

    if include["visits"]:
        rows = sorted(
            record["visits"],
            key=lambda x: x["date"],
            reverse=True,
        )[:10]

        section(
            "최근 진료 기록",
            [
                f"{x['date']} / {x['place']} / "
                f"{x['purpose']} / {x['note']}"
                for x in rows
            ],
        )

    if include["questions"]:
        section(
            "의료진에게 질문할 내용",
            [record["doctor_questions"]]
            if record["doctor_questions"]
            else [],
        )

    pdf.build(parts)
    return output.getvalue()


# ================================================
# 4개 탭
# ================================================

tab1, tab2, tab3, tab4 = st.tabs([
    "🗂️ 의료정보 관리",
    "🧪 나의 약물 분석",
    "📈 건강 타임라인",
    "📄 진료 준비",
])


# ================================================
# 탭 1. 개인 의료정보 관리
# ================================================

with tab1:
    record = get_record()
    st.subheader("복용 약물")

    with st.form(
        "record_add_drug",
        clear_on_submit=True,
    ):
        selected = st.selectbox(
            "의약품 선택",
            ["직접 입력"] + sorted(
                drug_df["제품명"]
                .dropna()
                .unique()
                .tolist()
            ),
        )

        custom = st.text_input(
            "목록에 없는 약 이름 (직접 입력 선택 시)",
            max_chars=120,
        )

        add_drug = st.form_submit_button(
            "약물 추가",
            type="primary",
        )

    if add_drug:
        name = (
            custom.strip()
            if selected == "직접 입력"
            else selected
        )

        if not name:
            st.warning("약 이름을 입력하세요.")
        elif name in record["drugs"]:
            st.info("이미 등록된 약입니다.")
        else:
            record["drugs"].append(name)
            apply_change(record)

    if record["drugs"]:
        st.write(
            "등록된 약: "
            + ", ".join(record["drugs"])
        )

        with st.form("record_edit_drug"):
            before = st.selectbox(
                "수정·삭제할 약",
                record["drugs"],
            )
            after = st.text_input(
                "수정할 이름",
                value=before,
                max_chars=120,
            )

            c1, c2 = st.columns(2)
            edit_drug = c1.form_submit_button(
                "이름 수정"
            )
            remove_drug = c2.form_submit_button(
                "선택 삭제"
            )

        if edit_drug:
            if not after.strip():
                st.warning(
                    "수정할 약 이름을 입력하세요."
                )
            elif (
                after.strip() != before
                and after.strip() in record["drugs"]
            ):
                st.warning(
                    "이미 등록된 이름입니다."
                )
            else:
                record["drugs"][
                    record["drugs"].index(before)
                ] = after.strip()
                apply_change(record)

        if remove_drug:
            record["drugs"].remove(before)
            apply_change(record)

    else:
        st.info("등록된 약물이 없습니다.")

    st.divider()

    # 질환·증상
    st.subheader("질환·증상")

    with st.form(
        "record_add_condition",
        clear_on_submit=True,
    ):
        choice = st.selectbox(
            "질환·증상 선택",
            ["직접 입력"] + sorted(
                condition_df["질병명"]
                .dropna()
                .unique()
                .tolist()
            ),
        )

        custom_condition = st.text_input(
            "목록에 없는 질환·증상",
            max_chars=120,
        )

        add_condition = st.form_submit_button(
            "질환·증상 추가",
            type="primary",
        )

    if add_condition:
        name = (
            custom_condition.strip()
            if choice == "직접 입력"
            else choice
        )

        if not name:
            st.warning(
                "질환·증상 이름을 입력하세요."
            )
        elif name in record["conditions"]:
            st.info("이미 등록된 항목입니다.")
        else:
            record["conditions"].append(name)
            apply_change(record)

    if record["conditions"]:
        st.write(
            "등록된 항목: "
            + ", ".join(record["conditions"])
        )

        with st.form("record_edit_condition"):
            before = st.selectbox(
                "수정·삭제할 질환",
                record["conditions"],
            )
            after = st.text_input(
                "수정할 질환 이름",
                value=before,
                max_chars=120,
            )

            c1, c2 = st.columns(2)
            edit_condition = c1.form_submit_button(
                "이름 수정"
            )
            remove_condition = c2.form_submit_button(
                "선택 삭제"
            )

        if edit_condition:
            if not after.strip():
                st.warning(
                    "수정할 이름을 입력하세요."
                )
            elif (
                after.strip() != before
                and after.strip() in record["conditions"]
            ):
                st.warning(
                    "이미 등록된 항목입니다."
                )
            else:
                record["conditions"][
                    record["conditions"].index(before)
                ] = after.strip()
                apply_change(record)

        if remove_condition:
            record["conditions"].remove(before)
            apply_change(record)

    st.divider()

    # 알레르기
    st.subheader("알레르기")
    st.caption(
        "표의 행을 추가·수정·삭제한 다음 저장하세요."
    )

    edited_allergies = st.data_editor(
        pd.DataFrame(
            record["allergies"],
            columns=["name", "reaction"],
        ),
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "name": "원인 물질",
            "reaction": "나타난 반응",
        },
        key="allergy_editor",
    )

    if st.button(
        "알레르기 변경 저장",
        key="save_allergies",
    ):
        record["allergies"] = cleaned_rows(
            edited_allergies,
            ["name", "reaction"],
        )
        apply_change(record)

    st.divider()

    # 진료 기록
    st.subheader("진료 기록")
    st.caption(
        "날짜는 YYYY-MM-DD 형식, "
        "기관명은 필수입니다."
    )

    edited_visits = st.data_editor(
        pd.DataFrame(
            record["visits"],
            columns=[
                "date", "place", "purpose", "note"
            ],
        ),
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "date": "진료일(YYYY-MM-DD)",
            "place": "기관명",
            "purpose": "진료 목적",
            "note": "메모",
        },
        key="visits_editor",
    )

    if st.button(
        "진료 기록 변경 저장",
        key="save_visits",
    ):
        rows = cleaned_rows(
            edited_visits,
            ["date", "place", "purpose", "note"],
        )

        proposed = dict(record, visits=rows)
        checked = normalize_record(proposed)

        if len(checked["visits"]) != len(rows):
            st.warning(
                "진료 날짜와 기관명을 확인하세요."
            )
        else:
            apply_change(checked)

    st.divider()

    # 백업
    st.subheader("가상 데이터 백업 및 삭제")

    st.download_button(
        "내 기록을 JSON으로 백업",
        data=json.dumps(
            get_record(),
            ensure_ascii=False,
            indent=2,
        ),
        file_name="my_medicare_backup.json",
        mime="application/json",
    )

    with st.expander("백업 파일에서 복원"):
        uploaded = st.file_uploader(
            "JSON 백업 파일",
            type=["json"],
            key="record_import",
        )

        if st.button(
            "선택한 백업 불러오기",
            disabled=uploaded is None,
        ):
            try:
                if uploaded.size > 1_000_000:
                    raise ValueError(
                        "파일이 너무 큽니다."
                    )

                content = json.loads(
                    uploaded.getvalue().decode("utf-8")
                )

                if not isinstance(content, dict):
                    raise ValueError(
                        "형식이 올바르지 않습니다."
                    )

                apply_change(
                    normalize_record(content)
                )

            except (
                UnicodeDecodeError,
                ValueError,
            ) as exc:
                st.error(
                    f"백업 파일 오류: {exc}"
                )

    with st.expander("내 기록 전체 삭제"):
        confirm = st.checkbox(
            "저장된 내 기록 전체 삭제에 동의합니다.",
            key="delete_confirm",
        )

        if st.button(
            "기록 전체 삭제",
            disabled=not confirm,
        ):
            try:
                delete_all()
                st.rerun()
            except MedicalStoreError as exc:
                st.error(str(exc))


# ================================================
# 탭 2. 약물 성분 분석
# ================================================

with tab2:
    record = get_record()
    st.subheader(
        "저장된 복용 약물 성분 비교"
    )

    if not record["drugs"]:
        st.info(
            "의료정보 관리 탭에서 "
            "복용 약물을 먼저 등록해 주세요."
        )
    else:
        selected = get_selected_drugs(
            drug_df,
            record["drugs"],
        )

        missing = [
            x for x in record["drugs"]
            if x not in selected["제품명"].tolist()
        ]

        if missing:
            st.warning(
                "자동 분석할 수 없는 약물: "
                + ", ".join(missing)
            )

        if selected.empty:
            st.info(
                "분석 가능한 등록 의약품이 없습니다."
            )
        else:
            duplicates, ingredient_map = (
                find_duplicates(selected)
            )

            a, b, c = st.columns(3)
            a.metric(
                "분석 제품",
                len(selected),
            )
            b.metric(
                "고유 성분",
                len(ingredient_map),
            )
            c.metric(
                "공통 성분",
                len(duplicates),
            )

            st.dataframe(
                selected[
                    ["제품명", "카테고리", "성분"]
                ],
                hide_index=True,
                use_container_width=True,
            )

            if duplicates:
                st.warning(
                    "여러 의약품에 공통으로 "
                    "나타난 성분이 있습니다."
                )

                st.dataframe(
                    pd.DataFrame([
                        {
                            "공통 성분": name,
                            "포함 제품": ", ".join(
                                sorted(products)
                            ),
                        }
                        for name, products
                        in sorted(duplicates.items())
                    ]),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.success(
                    "성분명 기준 공통 성분이 없습니다."
                )

            st.caption(
                "공통 성분이 있어도 실제 병용 위험 "
                "또는 용량 중복 여부를 "
                "자동 판단할 수 없습니다."
            )

            with st.expander(
                "성분 사전 내용과 연결해 보기"
            ):
                known = ingredient_df[
                    ingredient_df["성분명"].isin(
                        ingredient_map
                    )
                ]

                if known.empty:
                    st.info(
                        "연결되는 성분 사전 항목이 없습니다."
                    )
                else:
                    st.dataframe(
                        known[
                            ["성분명", "분류", "설명"]
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )


# ================================================
# 탭 3. 건강 타임라인
# ================================================

with tab3:
    record = get_record()
    st.subheader("건강 변화 기록")

    with st.form(
        "timeline_add_form",
        clear_on_submit=True,
    ):
        day = st.date_input(
            "기록 날짜",
            value=date.today(),
        )
        kind = st.selectbox(
            "기록 종류",
            ["증상", "복약 변경", "진료", "기타"],
        )
        title = st.text_input(
            "기록 내용",
            max_chars=120,
            placeholder="예: 두통, 복용 시작",
        )
        severity = st.slider(
            "불편감 정도 (0~10, 증상 기록에 사용)",
            0, 10, 0,
        )
        note = st.text_area(
            "추가 메모",
            max_chars=500,
        )
        add_timeline = st.form_submit_button(
            "기록 추가",
            type="primary",
        )

    if add_timeline:
        if not title.strip():
            st.warning(
                "기록 내용을 입력해 주세요."
            )
        else:
            record["timeline"].append({
                "date": day.isoformat(),
                "kind": kind,
                "title": title.strip(),
                "severity": severity,
                "note": note.strip(),
            })
            apply_change(record)

    if record["timeline"]:
        data = pd.DataFrame(
            record["timeline"]
        ).sort_values(
            "date",
            ascending=False,
        )

        st.write(
            f"전체 기록: {len(data)}건"
        )

        st.dataframe(
            data,
            hide_index=True,
            use_container_width=True,
        )

        symptoms = data[
            data["kind"] == "증상"
        ].copy()

        if not symptoms.empty:
            symptoms["date"] = pd.to_datetime(
                symptoms["date"]
            )

            daily = symptoms.groupby(
                "date"
            )["severity"].mean()

            st.subheader(
                "날짜별 증상 불편감 (평균)"
            )
            st.line_chart(daily)

        st.caption(
            "약물 변경과 증상 발생 사이의 "
            "인과관계를 추정하지 않습니다."
        )

        st.subheader(
            "기존 기록 수정·삭제"
        )

        edited_timeline = st.data_editor(
            pd.DataFrame(
                record["timeline"],
                columns=[
                    "date", "kind", "title",
                    "severity", "note"
                ],
            ),
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            column_config={
                "date": "날짜(YYYY-MM-DD)",
                "kind": "종류",
                "title": "내용",
                "severity": st.column_config.NumberColumn(
                    "불편감 0~10",
                    min_value=0,
                    max_value=10,
                    step=1,
                ),
                "note": "메모",
            },
            key="timeline_editor",
        )

        if st.button(
            "타임라인 변경 저장",
            key="save_timeline",
        ):
            rows = cleaned_rows(
                edited_timeline,
                [
                    "date", "kind", "title",
                    "severity", "note"
                ],
            )

            checked = normalize_record(
                dict(record, timeline=rows)
            )

            if (
                len(checked["timeline"])
                != len(rows)
            ):
                st.warning(
                    "날짜(YYYY-MM-DD), 기록 내용, "
                    "불편감 점수를 확인해 주세요."
                )
            else:
                apply_change(checked)

    else:
        st.info(
            "아직 기록이 없습니다. "
            "위에서 첫 기록을 추가하세요."
        )


# ================================================
# 탭 4. 진료 준비 및 PDF
# ================================================

with tab4:
    record = get_record()
    st.subheader("진료 준비 요약서")

    st.caption(
        "요약서에 넣을 항목만 선택하고, "
        "의료진에게 보여주기 전 내용을 확인하세요."
    )

    with st.form("doctor_questions_form"):
        questions = st.text_area(
            "의료진에게 질문할 내용",
            value=record["doctor_questions"],
            max_chars=2000,
            height=140,
        )

        save_questions = st.form_submit_button(
            "질문 내용 저장",
            type="primary",
        )

    if save_questions:
        record["doctor_questions"] = (
            questions.strip()
        )
        apply_change(record)

    fields = {
        "drugs": "복용 약물",
        "conditions": "질환·증상",
        "allergies": "알레르기",
        "timeline": "최근 건강 변화(최대 15건)",
        "visits": "최근 진료 기록(최대 10건)",
        "questions": "질문 내용",
    }

    include = {
        name: st.checkbox(
            label,
            value=True,
            key=f"pdf_{name}",
        )
        for name, label in fields.items()
    }

    if any(include.values()):
        try:
            st.download_button(
                "진료용 요약서 PDF 저장",
                data=pdf_summary(
                    record, include
                ),
                file_name="my_medicare_visit_summary.pdf",
                mime="application/pdf",
                type="primary",
            )
        except (OSError, ValueError) as exc:
            st.error(
                "PDF 생성 실패: "
                f"{type(exc).__name__}"
            )
    else:
        st.info(
            "요약서에 포함할 항목을 "
            "하나 이상 선택해 주세요."
        )

    st.warning(
        "개인정보가 포함된 문서는 공유·전송 전에 "
        "수신자와 내용을 확인하세요."
    )
