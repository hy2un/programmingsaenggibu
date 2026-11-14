"""My MediCare 개인 건강 기록 저장 공통 모듈 (가상 데이터 시연용).

Google OIDC 로그인과 Supabase REST 저장소가 모두 설정되었을 때만 영구 저장.
설정이 없을 때에는 현재 Streamlit 세션에만 보관합니다.
"""

from copy import deepcopy
from datetime import date

import requests
import streamlit as st


class MedicalStoreError(Exception):
    """저장소 연결 또는 읽기/쓰기 실패."""


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


def normalize_record(record):
    """기존 기록이나 가져온 JSON을 허용된 필드로 정리."""
    if not isinstance(record, dict):
        return empty_record()

    result = empty_record()
    result["drugs"] = unique_strings(record.get("drugs", []))
    result["conditions"] = unique_strings(record.get("conditions", []))
    result["doctor_questions"] = clean_text(
        record.get("doctor_questions", ""), 2000
    )

    for row in record.get("allergies", [])[:200]:
        if isinstance(row, dict):
            name = clean_text(row.get("name"), 120)
            if name:
                result["allergies"].append({
                    "name": name,
                    "reaction": clean_text(row.get("reaction"), 200),
                })

    for row in record.get("visits", [])[:300]:
        if isinstance(row, dict):
            day = valid_date(row.get("date"))
            place = clean_text(row.get("place"), 120)
            if day and place:
                result["visits"].append({
                    "date": day,
                    "place": place,
                    "purpose": clean_text(row.get("purpose"), 200),
                    "note": clean_text(row.get("note"), 500),
                })

    for row in record.get("timeline", [])[:500]:
        if isinstance(row, dict):
            day = valid_date(row.get("date"))
            title = clean_text(row.get("title"), 120)
            if not (day and title):
                continue
            try:
                severity = max(0, min(10, int(row.get("severity", 0))))
            except (TypeError, ValueError):
                severity = 0
            result["timeline"].append({
                "date": day,
                "kind": clean_text(row.get("kind"), 30) or "기타",
                "title": title,
                "severity": severity,
                "note": clean_text(row.get("note"), 500),
            })
    return result


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
    sub = clean_text(st.user.get("sub", ""), 200)
    return f"google:{sub}" if sub else ""


def cloud_ready():
    return bool(
        current_user_id()
        and secret("SUPABASE_URL")
        and secret("SUPABASE_SERVICE_ROLE_KEY")
    )


def _request(method, params=None, payload=None):
    """비밀키는 Streamlit 서버에서만 사용하고 브라우저에 전달하지 않음."""
    url = str(secret("SUPABASE_URL", "")).rstrip("/")
    key = str(secret("SUPABASE_SERVICE_ROLE_KEY", ""))
    if not url.startswith("https://") or not key:
        raise MedicalStoreError("저장소 주소 또는 비밀키 설정이 올바르지 않습니다.")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if method == "POST":
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
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
    except requests.RequestException as exc:
        # 서버 응답 본문에 개인 기록이 포함될 가능성을 피하기 위해 상세 정보 미표시
        raise MedicalStoreError("클라우드 저장소 통신에 실패했습니다.") from exc


def _load_cloud(user_id):
    response = _request(
        "GET",
        params={"user_id": f"eq.{user_id}", "select": "data", "limit": "1"},
    )
    try:
        rows = response.json()
        if not isinstance(rows, list):
            raise ValueError("Unexpected response")
        return normalize_record(rows[0].get("data", {})) if rows else empty_record()
    except (ValueError, TypeError, AttributeError, IndexError) as exc:
        raise MedicalStoreError("저장된 기록을 읽을 수 없습니다.") from exc


def init_record():
    """앱의 어느 페이지에서든 한 번만 불러오고 메인과 목록을 동기화."""
    owner = current_user_id() or "demo-session"
    if st.session_state.get("medical_record_owner") != owner:
        record = _load_cloud(owner) if cloud_ready() else empty_record()
        st.session_state["medical_record"] = record
        st.session_state["medical_record_owner"] = owner
    record = st.session_state["medical_record"]
    st.session_state["my_drugs"] = list(record["drugs"])
    st.session_state["my_conditions"] = list(record["conditions"])
    return deepcopy(record)


def get_record():
    init_record()
    return deepcopy(st.session_state["medical_record"])


def save_record(data):
    """원격 저장이 실패하면 화면의 데이터도 바꾸지 않음."""
    record = normalize_record(data)
    owner = current_user_id()
    if cloud_ready():
        _request(
            "POST",
            params={"on_conflict": "user_id"},
            payload={"user_id": owner, "data": record},
        )
    st.session_state["medical_record"] = record
    st.session_state["medical_record_owner"] = owner or "demo-session"
    st.session_state["my_drugs"] = list(record["drugs"])
    st.session_state["my_conditions"] = list(record["conditions"])


def delete_all():
    """본인 기록만 삭제. 설정되지 않은 상태에서는 세션 삭제."""
    owner = current_user_id()
    if cloud_ready():
        _request("DELETE", params={"user_id": f"eq.{owner}"})
    st.session_state["medical_record"] = empty_record()
    st.session_state["medical_record_owner"] = owner or "demo-session"
    st.session_state["my_drugs"] = []
    st.session_state["my_conditions"] = []


def save_with_message(data):
    """Streamlit UI에서 공통 예외를 안전하게 표시하고 성공 여부를 반환."""
    try:
        save_record(data)
        return True
    except MedicalStoreError as exc:
        st.error(str(exc) + " 기존 기록은 변경하지 않았습니다.")
        return False
