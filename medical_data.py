"""My MediCare 개인 의료정보 저장 관리 모듈.

Google 로그인 사용자별로 Supabase에 기록을 저장합니다.
새 탭이나 새 세션에서 같은 계정의 기록을 불러옵니다.
"""

from copy import deepcopy
from datetime import date

import requests
import streamlit as st


# ==================================================
# 1. 오류 처리
# ==================================================

class MedicalStoreError(Exception):
    """의료정보 저장 및 불러오기 오류."""
    pass


# ==================================================
# 2. 기본 데이터 구조
# ==================================================

def empty_record():
    return {
        "drugs": [],
        "conditions": [],
        "allergies": [],
        "visits": [],
        "timeline": [],
        "doctor_questions": "",
    }


def clean_text(value, limit=300):
    return str(value or "").strip()[:limit]


def unique_strings(values):
    result = []

    if not isinstance(values, list):
        return result

    for item in values[:300]:
        value = clean_text(item, 120)

        if value and value not in result:
            result.append(value)

    return result


def valid_date(value):
    value = clean_text(value, 10)

    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return ""


# ==================================================
# 3. 의료정보 데이터 정리
# ==================================================

def normalize_record(record):

    if not isinstance(record, dict):
        return empty_record()

    result = empty_record()

    result["drugs"] = unique_strings(
        record.get("drugs", [])
    )

    result["conditions"] = unique_strings(
        record.get("conditions", [])
    )

    result["doctor_questions"] = clean_text(
        record.get("doctor_questions", ""),
        2000,
    )

    # 알레르기
    allergies = record.get("allergies", [])

    if isinstance(allergies, list):
        for row in allergies[:200]:

            if not isinstance(row, dict):
                continue

            name = clean_text(
                row.get("name"),
                120,
            )

            if name:
                result["allergies"].append({
                    "name": name,
                    "reaction": clean_text(
                        row.get("reaction"),
                        200,
                    ),
                })

    # 진료 기록
    visits = record.get("visits", [])

    if isinstance(visits, list):
        for row in visits[:300]:

            if not isinstance(row, dict):
                continue

            day = valid_date(
                row.get("date")
            )

            place = clean_text(
                row.get("place"),
                120,
            )

            if day and place:
                result["visits"].append({
                    "date": day,
                    "place": place,
                    "purpose": clean_text(
                        row.get("purpose"),
                        200,
                    ),
                    "note": clean_text(
                        row.get("note"),
                        500,
                    ),
                })

    # 건강 타임라인
    timeline = record.get("timeline", [])

    if isinstance(timeline, list):
        for row in timeline[:500]:

            if not isinstance(row, dict):
                continue

            day = valid_date(
                row.get("date")
            )

            title = clean_text(
                row.get("title"),
                120,
            )

            if not day or not title:
                continue

            try:
                severity = max(
                    0,
                    min(
                        10,
                        int(row.get("severity", 0)),
                    ),
                )
            except (ValueError, TypeError):
                severity = 0

            result["timeline"].append({
                "date": day,
                "kind": clean_text(
                    row.get("kind"),
                    30,
                ) or "기타",
                "title": title,
                "severity": severity,
                "note": clean_text(
                    row.get("note"),
                    500,
                ),
            })

    return result


# ==================================================
# 4. Streamlit Secrets 설정
# ==================================================

def secret(name, default=""):

    try:
        return st.secrets.get(name, default)

    except (FileNotFoundError, KeyError):
        return default


def login_configured():
    return bool(secret("auth"))


def is_logged_in():

    if not login_configured():
        return False

    return bool(
        getattr(
            st.user,
            "is_logged_in",
            False,
        )
    )


# ==================================================
# 5. Google 사용자 식별
# ==================================================

def current_user_id():

    if not is_logged_in():
        return ""

    user_sub = clean_text(
        st.user.get("sub", ""),
        200,
    )

    if not user_sub:
        return ""

    return f"google:{user_sub}"


# ==================================================
# 6. Supabase 연결 정보
# ==================================================

def _storage_details():

    url = str(
        secret("SUPABASE_URL", "")
    ).strip().rstrip("/")

    # 새로운 Supabase Secret Key
    new_key = str(
        secret("SUPABASE_SECRET_KEY", "")
    ).strip()

    # 기존 키도 호환
    old_key = str(
        secret("SUPABASE_SERVICE_ROLE_KEY", "")
    ).strip()

    key = new_key or old_key

    return url, key


def cloud_ready():

    url, key = _storage_details()

    return bool(
        current_user_id()
        and url.startswith("https://")
        and key
    )


# ==================================================
# 7. Supabase REST API 통신
# ==================================================

def _request(method, params=None, payload=None):

    url, key = _storage_details()

    if not url.startswith("https://"):
        raise MedicalStoreError(
            "Supabase 프로젝트 URL을 확인하세요."
        )

    if not key:
        raise MedicalStoreError(
            "Supabase Secret Key가 등록되지 않았습니다."
        )

    if key.startswith("sb_publishable_"):
        raise MedicalStoreError(
            "공개용 키가 아닌 서버용 Secret Key를 사용하세요."
        )

    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # 새 sb_secret 키는 JWT 형식이 아닙니다.
    # 따라서 Authorization에 넣지 않습니다.
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = (
            f"Bearer {key}"
        )

    if method == "POST":
        headers["Prefer"] = (
            "resolution=merge-duplicates,"
            "return=minimal"
        )

    try:
        response = requests.request(
            method=method,
            url=f"{url}/rest/v1/medical_records",
            params=params,
            json=payload,
            headers=headers,
            timeout=15,
        )

        response.raise_for_status()

        return response

    except requests.HTTPError as error:

        status = getattr(
            error.response,
            "status_code",
            "알 수 없음",
        )

        raise MedicalStoreError(
            f"Supabase 오류: HTTP {status}. "
            "URL, API 키, 테이블 권한을 확인하세요."
        ) from error

    except requests.RequestException as error:

        raise MedicalStoreError(
            "Supabase 서버와 통신하지 못했습니다."
        ) from error


# ==================================================
# 8. 클라우드 저장 데이터 불러오기
# ==================================================

def _load_cloud(user_id):

    response = _request(
        "GET",
        params={
            "user_id": f"eq.{user_id}",
            "select": "data",
            "limit": "1",
        },
    )

    try:
        rows = response.json()

        if not isinstance(rows, list):
            raise ValueError("잘못된 응답")

        if not rows:
            return empty_record()

        return normalize_record(
            rows[0].get("data", {})
        )

    except (
        ValueError,
        TypeError,
        AttributeError,
        IndexError,
    ) as error:

        raise MedicalStoreError(
            "저장된 의료정보를 읽지 못했습니다."
        ) from error


# ==================================================
# 9. 세션 시작 및 새 탭 데이터 불러오기
# ==================================================

def init_record():

    user_id = current_user_id()

    if is_logged_in() and not user_id:
        raise MedicalStoreError(
            "Google 계정 식별자를 확인하지 못했습니다. "
            "다시 로그인하세요."
        )

    owner = user_id or "demo-session"

    mode = (
        "cloud"
        if cloud_ready()
        else "demo"
    )

    cache_key = (owner, mode)

    # 새 브라우저 탭에서는 별도의 세션이 시작됩니다.
    # 로그인과 Supabase가 연결되어 있다면
    # 저장된 기록을 다시 가져옵니다.

    if (
        st.session_state.get(
            "medical_record_cache_key"
        ) != cache_key
    ):

        if mode == "cloud":
            record = _load_cloud(user_id)

        else:
            record = empty_record()

        st.session_state[
            "medical_record"
        ] = record

        st.session_state[
            "medical_record_cache_key"
        ] = cache_key

    record = st.session_state[
        "medical_record"
    ]

    # 기존 메인 페이지와 데이터 연동
    st.session_state["my_drugs"] = list(
        record["drugs"]
    )

    st.session_state["my_conditions"] = list(
        record["conditions"]
    )

    return deepcopy(record)


def get_record():
    return init_record()


# ==================================================
# 10. 서버 기록 새로 불러오기
# ==================================================

def refresh_record():

    st.session_state.pop(
        "medical_record_cache_key",
        None,
    )

    return init_record()


# ==================================================
# 11. 의료정보 영구 저장
# ==================================================

def save_record(data):

    record = normalize_record(data)

    user_id = current_user_id()

    # 로그인이 설정된 경우 로그인 요구
    if login_configured() and not is_logged_in():
        raise MedicalStoreError(
            "Google 로그인 후 저장할 수 있습니다."
        )

    if is_logged_in() and not user_id:
        raise MedicalStoreError(
            "Google 사용자 정보를 확인하지 못했습니다."
        )

    # 로그인만 되었고 데이터베이스가 없으면
    # 저장 성공으로 처리하지 않습니다.
    if is_logged_in() and not cloud_ready():
        raise MedicalStoreError(
            "Google 로그인은 완료되었지만 "
            "Supabase 저장소가 연결되지 않았습니다. "
            "Streamlit Secrets를 확인하세요."
        )

    if cloud_ready():

        # 사용자별 기록 저장 또는 갱신
        _request(
            "POST",
            params={
                "on_conflict": "user_id",
            },
            payload={
                "user_id": user_id,
                "data": record,
            },
        )

        # 실제 저장 여부 확인
        saved_record = _load_cloud(user_id)

        if saved_record != record:
            raise MedicalStoreError(
                "저장된 데이터가 일치하지 않습니다. "
                "서버 기록을 다시 확인하세요."
            )

    # 정상적으로 저장된 경우에만
    # 현재 화면의 데이터를 갱신합니다.
    st.session_state[
        "medical_record"
    ] = record

    st.session_state[
        "medical_record_cache_key"
    ] = (
        user_id or "demo-session",
        "cloud" if cloud_ready() else "demo",
    )

    st.session_state["my_drugs"] = list(
        record["drugs"]
    )

    st.session_state["my_conditions"] = list(
        record["conditions"]
    )


# ==================================================
# 12. 사용자 기록 전체 삭제
# ==================================================

def delete_all():

    user_id = current_user_id()

    if login_configured() and not is_logged_in():
        raise MedicalStoreError(
            "Google 로그인 후 삭제할 수 있습니다."
        )

    if is_logged_in() and not cloud_ready():
        raise MedicalStoreError(
            "Supabase 연결이 없어 "
            "저장된 기록을 삭제할 수 없습니다."
        )

    if cloud_ready():

        _request(
            "DELETE",
            params={
                "user_id": f"eq.{user_id}",
            },
        )

        # 삭제 후 서버를 다시 조회
        remaining = _load_cloud(user_id)

        if remaining != empty_record():
            raise MedicalStoreError(
                "서버 기록 삭제를 확인하지 못했습니다."
            )

    st.session_state[
        "medical_record"
    ] = empty_record()

    st.session_state[
        "medical_record_cache_key"
    ] = (
        user_id or "demo-session",
        "cloud" if cloud_ready() else "demo",
    )

    st.session_state["my_drugs"] = []
    st.session_state["my_conditions"] = []


# ==================================================
# 13. 저장 결과 메시지
# ==================================================

def save_with_message(data):

    try:
        save_record(data)
        return True

    except MedicalStoreError as error:
        st.error(str(error))
        return False
