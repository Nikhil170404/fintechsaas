"""Unit tests for billing module."""
import os
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("FLASK_ENV", "testing")


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Redirect DB to a temp file per test."""
    db_path = tmp_path / "test.db"
    import modules.db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    db_mod.init_db()
    # Re-run billing table creation
    from modules.billing import _ensure_tables
    _ensure_tables()


def _make_tenant():
    from modules.db import create_tenant
    return create_tenant("Test Co", f"test_{int(time.time() * 1000)}")


class TestPlans:
    def test_all_plans_have_limits(self):
        from modules.billing import PLANS
        for name, plan in PLANS.items():
            assert "limits" in plan
            assert "price_inr" in plan

    def test_free_has_client_limit(self):
        from modules.billing import PLANS
        assert PLANS["free"]["limits"]["clients"] > 0

    def test_enterprise_unlimited(self):
        from modules.billing import PLANS
        assert PLANS["enterprise"]["limits"]["clients"] == -1


class TestSubscription:
    def test_new_tenant_gets_trial(self):
        from modules.billing import get_subscription, effective_plan
        t = _make_tenant()
        sub = get_subscription(t)
        assert sub["status"] == "trial"
        assert effective_plan(t) == "pro"   # pro during trial

    def test_upgrade_plan(self):
        from modules.billing import update_subscription, get_subscription, effective_plan
        t = _make_tenant()
        update_subscription(t, "starter", "active")
        assert get_subscription(t)["plan"] == "starter"
        assert effective_plan(t) == "starter"

    def test_trial_expiry(self):
        from modules.billing import update_subscription, get_subscription, effective_plan, _connect
        t = _make_tenant()
        # Force trial to expire
        conn = _connect()
        conn.execute("UPDATE subscriptions SET trial_ends_at = ? WHERE tenant_id = ?",
                     (int(time.time()) - 1, t))
        conn.commit()
        conn.close()
        sub = get_subscription(t)
        assert effective_plan(t) == sub["plan"]


class TestUsage:
    def test_increment_and_check(self):
        from modules.billing import increment_usage, _get_usage
        t = _make_tenant()
        month = time.strftime("%Y-%m")
        increment_usage(t, "statements_per_month", 5)
        assert _get_usage(t, month, "statements_per_month") == 5
        increment_usage(t, "statements_per_month", 3)
        assert _get_usage(t, month, "statements_per_month") == 8

    def test_limit_check(self):
        from modules.billing import check_limit, update_subscription, increment_usage
        from modules.billing import PLANS
        t = _make_tenant()
        update_subscription(t, "free", "active")
        free_limit = PLANS["free"]["limits"]["statements_per_month"]
        # Under limit
        allowed, used, limit = check_limit(t, "statements_per_month")
        assert allowed is True
        assert limit == free_limit
        # Exceed limit
        increment_usage(t, "statements_per_month", free_limit)
        allowed, used, limit = check_limit(t, "statements_per_month")
        assert allowed is False


class TestAuditChain:
    def test_chain_ok(self):
        from modules.audit_chain import _ensure_table, add, verify_chain
        _ensure_table()
        t = _make_tenant()
        add(t, "1.2.3.4", "user", "ACTION_A", "detail")
        add(t, "1.2.3.4", "user", "ACTION_B", "detail2")
        result = verify_chain(t)
        assert result["ok"] is True
        assert result["entries"] == 2

    def test_chain_tamper_detected(self):
        from modules.audit_chain import _ensure_table, add, verify_chain
        from modules.db import _connect
        _ensure_table()
        t = _make_tenant()
        add(t, "1.2.3.4", "user", "ACTION", "original")
        # Tamper with the last entry
        conn = _connect()
        conn.execute("UPDATE audit_chain SET detail = 'tampered' WHERE tenant_id = ?", (t,))
        conn.commit()
        conn.close()
        result = verify_chain(t)
        assert result["ok"] is False
        assert result["first_tampered_id"] is not None
