"""My MediCare: Google 로그인 계정별 Supabase 건강기록 저장 모듈.

의료정보 및 이메일은 Streamlit 서버에서만 전용 API 키로 처리합니다.
실제 환자정보가 아닌 가상 정보로 동작을 검증하세요.
"""

from copy import deepcopy
from datetime import date
import requests
import streamlit as st


class MedicalStoreError(Exception):
    """저장·조회·접근 관련 오류."""


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
    if isinstance(values, list):
        for item in values[:300]:
            value = clean_text(item, 120)
            if value and value not in result:
                result.append(value)
    return result


def valid_date(value):
    try:
        return date.fromisoformat(
            clean_text(value, 10)
        ).isoformat()
    except (TypeError, ValueError):
        return ""


def normalize_record(record):
    if not isinstance(record, dict):
        return empty_record()

    result = empty_record()
    result["drugs"] = unique_strings(
        record.get("drugs")
    )
    result["conditions"] = unique_strings(
        record.get("conditions")
    )
    result["doctor_questions"] = clean_text(
        record.get("doctor_questions"), 2000
    )

    allergies = record.get("allergies")
    for row in (
        allergies[:200]
        if isinstance(allergies, list)
        else []
    ):
        if not isinstance(row, dict):
            continue
        name = clean_text(row.get("name"), 120)
        if name:
            result["allergies"].append({
                "name": name,
                "reaction": clean_text(
                    row.get("reaction"), 200
                ),
            })

    visits = record.get("visits")
    for row in (
        visits[:300]
        if isinstance(visits, list)
        else []
    ):
        if not isinstance(row, dict):
            continue
        day = valid_date(row.get("date"))
        place = clean_text(
            row.get("place"), 120
        )
        if day and place:
            result["visits"].append({
                "date": day,
                "place": place,
                "purpose": clean_text(
                    row.get("purpose"), 200
                ),
                "note": clean_text(
                    row.get("note"), 500
                ),
            })

    timeline = record.get("timeline")
    for row in (
        timeline[:500]
        if isinstance(timeline, list)
        else []
    ):
        if not isinstance(row, dict):
            continue

        day = valid_date(row.get("date"))
        title = clean_text(
            row.get("title"), 120
        )
        if not day or not title:
            continue

        try:
            severity = max(
                0, min(
                    10,
                    int(row.get("severity", 0))
                )
            )
        except (TypeError, ValueError):
            severity = 0

        result["timeline"].append({
            "date": day,
            "kind": clean_text(
                row.get("kind"), 30
            ) or "기타",
            "title": title,
            "severity": severity,
            "note": clean_text(
                row.get("note"), 500
            ),
        })

    return result


# ================================================
# Google 로그인 및 인증
# ================================================

def secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except (FileNotFoundError, KeyError):
        return default


def login_configured():
    return bool(secret("auth"))


def is_logged_in():
    return login_configured() and bool(
        getattr(st.user, "is_logged_in", False)
    )


def current_user_id():
    if not is_logged_in():
        return ""
    sub = clean_text(
        st.user.get("sub", ""), 200
    )
    return "google:" + sub if sub else ""


def current_user_email():
    """Google 이메일은 DB의 email 컬럼에만 저장."""
    if not is_logged_in():
        return ""
    return clean_text(
        st.user.get("email", ""), 254
    ).lower()


# ================================================
# Supabase 연결 설정
# ================================================

def _credentials():
    url = clean_text(
        secret("SUPABASE_URL"), 500
    ).rstrip("/")

    key = str(
        secret("SUPABASE_SECRET_KEY")
        or secret("SUPABASE_SERVICE_ROLE_KEY")
    ).strip()

    return url, key


def cloud_ready():
    """설정 존재 여부. 실제 접속은 init_record에서 확인."""
    url, key = _credentials()
    return bool(
        current_user_id()
        and url.startswith("https://")
        and key
    )


# ================================================
# Supabase API
# ================================================

def _request(
    method, *,
    params=None,
    payload=None,
):
    url, key = _credentials()

    if not url.startswith("https://") or not key:
        raise MedicalStoreError(
            "Streamlit Secrets의 Supabase URL과 "
            "Secret Key를 확인하세요."
        )

    if key.startswith("sb_publishable_"):
        raise MedicalStoreError(
            "공개용 키가 아닌 sb_secret_ 형식의 "
            "서버용 키를 사용하세요."
        )

    headers = {
        "apikey": key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # 새로운 sb_secret_ 키는 JWT가 아닙니다.
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"

    if method == "POST":
        headers["Prefer"] = (
            "resolution=merge-duplicates,"
            "return=minimal"
        )

    try:
        response = requests.request(
            method,
            f"{url}/rest/v1/medical_records",
            params=params,
            json=payload,
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        return response

    except requests.HTTPError as exc:
        status = getattr(
            exc.response, "status_code", "?"
        )
        raise MedicalStoreError(
            f"Supabase HTTP {status}: "
            "키, email 컬럼, 테이블 권한을 확인하세요."
        ) from exc

    except requests.RequestException as exc:
        raise MedicalStoreError(
            "Supabase 서버 연결에 실패했습니다."
        ) from exc


# ================================================
# 기록 조회
# ================================================

def _load_cloud(user_id):
    response = _request(
        "GET",
        params={
            "user_id": f"eq.{user_id}",
            "select": "data,email",
            "limit": "1",
        },
    )

    try:
        rows = response.json()
        if not isinstance(rows, list):
            raise ValueError("응답 형식 오류")

        return (
            normalize_record(
                rows[0].get("data")
            )
            if rows
            else empty_record()
        )

    except (
        ValueError,
        TypeError,
        IndexError,
        AttributeError,
    ) as exc:
        raise MedicalStoreError(
            "저장된 의료정보를 해석하지 못했습니다."
        ) from exc


# ================================================
# 세션 초기화 및 기록 불러오기
# ================================================

def init_record():
    user_id = current_user_id()

    if is_logged_in() and not user_id:
        raise MedicalStoreError(
            "Google 사용자 식별자를 찾을 수 없습니다. "
            "다시 로그인하세요."
        )

    mode = "cloud" if cloud_ready() else "demo"
    owner = user_id or "demo-session"
    cache_key = (owner, mode)

    if (
        st.session_state.get(
            "medical_record_cache_key"
        ) != cache_key
    ):
        record = (
            _load_cloud(user_id)
            if mode == "cloud"
            else empty_record()
        )
        st.session_state["medical_record"] = record
        st.session_state[
            "medical_record_cache_key"
        ] = cache_key

    record = st.session_state["medical_record"]
    st.session_state["my_drugs"] = list(
        record["drugs"]
    )
    st.session_state["my_conditions"] = list(
        record["conditions"]
    )

    return deepcopy(record)


def get_record():
    return init_record()


def refresh_record():
    st.session_state.pop(
        "medical_record_cache_key", None
    )
    return init_record()


# ================================================
# Supabase 영구 저장 + 이메일 저장
# ================================================

def save_record(data):
    record = normalize_record(data)
    user_id = current_user_id()

    if login_configured() and not is_logged_in():
        raise MedicalStoreError(
            "Google 로그인 후 저장해 주세요."
        )

    if is_logged_in() and not user_id:
        raise MedicalStoreError(
            "Google 사용자 식별자를 확인할 수 없습니다."
        )

    if is_logged_in() and not cloud_ready():
        raise MedicalStoreError(
            "Google 로그인은 되었지만 "
            "Supabase 저장소가 연결되지 않았습니다."
        )

    if cloud_ready():
        email = current_user_email()

        if not email:
            raise MedicalStoreError(
                "Google 계정 이메일을 확인할 수 없습니다. "
                "다시 로그인하세요."
            )

        _request(
            "POST",
            params={
                "on_conflict": "user_id"
            },
            payload={
                "user_id": user_id,
                "email": email,
                "data": record,
            },
        )

        # 이메일과 의료정보가 실제로 저장됐는지 재확인
        confirmed = _request(
            "GET",
            params={
                "user_id": f"eq.{user_id}",
                "select": "data,email",
                "limit": "1",
            },
        )

        try:
            rows = confirmed.json()
            saved_ok = (
                len(rows) == 1
                and rows[0].get("email") == email
                and normalize_record(
                    rows[0].get("data")
                ) == record
            )
        except (
            TypeError,
            ValueError,
            IndexError,
            AttributeError,
        ):
            saved_ok = False

        if not saved_ok:
            raise MedicalStoreError(
                "Supabase에 저장된 이메일 또는 "
                "기록이 일치하지 않습니다."
            )

    st.session_state["medical_record"] = record
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


# ================================================
# 기록 전체 삭제
# ================================================

def delete_all():
    user_id = current_user_id()

    if login_configured() and not is_logged_in():
        raise MedicalStoreError(
            "Google 로그인 후 삭제할 수 있습니다."
        )

    if is_logged_in() and not cloud_ready():
        raise MedicalStoreError(
            "Supabase 미연결 상태에서는 "
            "계정 기록을 삭제할 수 없습니다."
        )

    if cloud_ready():
        _request(
            "DELETE",
            params={
                "user_id": f"eq.{user_id}"
            },
        )

        if _load_cloud(user_id) != empty_record():
            raise MedicalStoreError(
                "Supabase 기록 삭제를 확인하지 못했습니다."
            )

    st.session_state["medical_record"] = empty_record()
    st.session_state[
        "medical_record_cache_key"
    ] = (
        user_id or "demo-session",
        "cloud" if cloud_ready() else "demo",
    )
    st.session_state["my_drugs"] = []
    st.session_state["my_conditions"] = []


def save_with_message(data):
    try:
        save_record(data)
        return True
    except MedicalStoreError as exc:
        st.error(str(exc))
        return False
