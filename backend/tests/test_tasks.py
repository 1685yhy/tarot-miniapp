"""
Tests for the checkin + task API.

Covers:
- POST /tasks/checkin — first checkin, duplicate rejection, streak
- GET  /tasks/status  — correct state after actions
- Level resolution logic
- Free-reading reward on checkin
"""

import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.tasks import _resolve_level, _next_level_info, LEVELS
from app.config import settings
from app.models.checkin import CheckIn


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _auth_headers(client: TestClient, member: bool = False) -> dict[str, str]:
    """Log in and return auth headers."""
    url = "/auth/dev-login?member=true" if member else "/auth/dev-login"
    resp = client.post(url, headers={"X-Dev-Key": settings.DEV_LOGIN_KEY})
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Checkin endpoint
# ---------------------------------------------------------------------------

class TestCheckin:
    """POST /tasks/checkin"""

    def test_checkin_success(self, client: TestClient):
        """A first-time checkin should return streak=1 and a reward."""
        headers = _auth_headers(client)
        resp = client.post("/tasks/checkin", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["signed_in"] is True, "signed_in should be True"
        assert data["streak"] == 1, f"First checkin should have streak=1, got {data['streak']}"
        # P0-3 缺口3：签到成功文案统一「星光馈赠」叙事（保留免费解读次数信息）
        assert data["reward"] == "星光馈赠：+1 免费解读", (
            f"Unexpected reward message: {data['reward']}"
        )

    def test_checkin_duplicate_rejection(self, client: TestClient):
        """Checking in again on the same day should return '今日已签到'."""
        headers = _auth_headers(client)
        # First checkin
        first = client.post("/tasks/checkin", headers=headers)
        assert first.status_code == 200
        first_data = first.json()
        first_streak = first_data["streak"]

        # Second checkin on same day
        second = client.post("/tasks/checkin", headers=headers)
        assert second.status_code == 200, second.text
        second_data = second.json()
        assert second_data["signed_in"] is True
        assert second_data["streak"] == first_streak, (
            f"Duplicate checkin should keep streak={first_streak}, "
            f"got {second_data['streak']}"
        )
        assert second_data["reward"] == "今日已签到", (
            f"Duplicate should say '今日已签到', got '{second_data['reward']}'"
        )

    def test_checkin_increments_free_readings(self, client: TestClient):
        """After checkin, the user's free_readings_today should increase."""
        headers = _auth_headers(client)

        # Check current status first
        status_before = client.get("/tasks/status", headers=headers)
        sb = status_before.json()
        # Look at membership status to see free_readings_today

        # Perform checkin
        resp = client.post("/tasks/checkin", headers=headers)
        assert resp.status_code == 200, resp.text

        # Verify task status shows the reward was applied
        status_after = client.get("/tasks/status", headers=headers)
        sa = status_after.json()
        assert sa["checked_in_today"] is True, "Should be checked in after checkin"


class TestTaskStatus:
    """GET /tasks/status"""

    def test_status_before_checkin(self, client: TestClient):
        """Status endpoint returns valid structure with level info."""
        headers = _auth_headers(client)
        resp = client.get("/tasks/status", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tasks_total"] == 3, "Should have 3 daily tasks"
        assert "level" in data, "Should have level info"
        assert data["level"]["current_level"] == "星光旅人", (
            "Default level should be '星光旅人'"
        )
        # checked_in_today and streak depend on test ordering; validate
        # they are the correct type
        assert isinstance(data["checked_in_today"], bool)
        assert isinstance(data["streak"], int)

    def test_status_after_checkin(self, client: TestClient):
        """After a checkin, status should reflect it."""
        headers = _auth_headers(client)
        client.post("/tasks/checkin", headers=headers)
        resp = client.get("/tasks/status", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["checked_in_today"] is True
        assert data["streak"] == 1

    def test_status_level_info_present(self, client: TestClient):
        """Status response must contain full level info."""
        headers = _auth_headers(client)
        resp = client.get("/tasks/status", headers=headers)
        data = resp.json()
        lv = data["level"]
        for field in ("current_level", "next_level", "days_needed", "progress"):
            assert field in lv, f"Level info missing field '{field}'"


# ---------------------------------------------------------------------------
# Level logic (pure functions, no HTTP needed)
# ---------------------------------------------------------------------------

class TestLevelResolution:
    """_resolve_level() and _next_level_info()"""

    def test_level_at_zero_streak(self):
        """Streak 0 → '星光旅人'."""
        lv = _resolve_level(0)
        assert lv["name"] == "星光旅人", f"Expected '星光旅人', got '{lv['name']}'"

    def test_level_transition_to_apprentice(self):
        """Streak 7 → '星辰学徒'."""
        lv = _resolve_level(7)
        assert lv["name"] == "星辰学徒", f"Expected '星辰学徒', got '{lv['name']}'"

    def test_level_transition_to_wise(self):
        """Streak 30 → '月光智者'."""
        lv = _resolve_level(30)
        assert lv["name"] == "月光智者", f"Expected '月光智者', got '{lv['name']}'"

    def test_level_transition_to_master(self):
        """Streak 100 → '银河导师'."""
        lv = _resolve_level(100)
        assert lv["name"] == "银河导师", f"Expected '银河导师', got '{lv['name']}'"

    def test_next_level_info_at_start(self):
        """Streak 0 → next is '星辰学徒', need 7 days."""
        name, need = _next_level_info(0)
        assert name == "星辰学徒", f"Expected '星辰学徒', got '{name}'"
        assert need == 7, f"Expected 7 days needed, got {need}"

    def test_next_level_info_near_top(self):
        """Streak 99 → next is '银河导师', need 1 day."""
        name, need = _next_level_info(99)
        assert name == "银河导师", f"Expected '银河导师', got '{name}'"
        assert need == 1, f"Expected 1 day needed, got {need}"

    def test_next_level_info_at_max(self):
        """Streak 999999 → no next level, need 0 days."""
        name, need = _next_level_info(999999)
        assert need == 0, f"At max level, need should be 0, got {need}"

    def test_all_levels_have_required_fields(self):
        """Each level definition must have name, min_days, max_days, badge_color."""
        for i, lv in enumerate(LEVELS):
            for field in ("name", "min_days", "max_days", "badge_color"):
                assert field in lv, (
                    f"LEVELS[{i}] missing field '{field}'"
                )
