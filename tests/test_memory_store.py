"""Tests for MemoryStore persistence, baselines, patterns, and feedback."""

import json
from datetime import datetime, timedelta

import pytest

from src.memory.models import Baseline, Observation, Pattern, UserFeedback
from src.memory.store import MemoryStore
from tests.conftest import seed_observations


class TestStoreInitialization:
    def test_creates_directory(self, tmp_path):
        store_dir = tmp_path / "new_dir"
        assert not store_dir.exists()
        MemoryStore(data_dir=store_dir)
        assert store_dir.exists()

    def test_loads_empty(self, memory_store):
        assert memory_store._observations == []
        assert memory_store._baselines == {}
        assert memory_store._patterns == {}
        assert memory_store._feedback == []


class TestPersistenceRoundtrip:
    def test_observations_persist(self, tmp_path):
        store_dir = tmp_path / "data"
        store = MemoryStore(data_dir=store_dir)

        obs = Observation(agent="test", metric="val", value=42.0)
        store.record_observation(obs)

        # Reload from disk
        store2 = MemoryStore(data_dir=store_dir)
        assert len(store2._observations) == 1
        assert store2._observations[0].value == 42.0

    def test_baselines_persist(self, tmp_path):
        store_dir = tmp_path / "data"
        store = MemoryStore(data_dir=store_dir)

        obs = Observation(agent="test", metric="val", value=10.0)
        store.record_observation(obs)

        store2 = MemoryStore(data_dir=store_dir)
        bl = store2.get_baseline("test", "val")
        assert bl is not None
        assert bl.mean == 10.0

    def test_patterns_persist(self, tmp_path):
        store_dir = tmp_path / "data"
        store = MemoryStore(data_dir=store_dir)

        p = Pattern(agent="test", name="p1", description="test",
                     condition={"k": "v"}, action="ignore", confidence=0.8)
        store.add_pattern(p)

        store2 = MemoryStore(data_dir=store_dir)
        assert store2.get_pattern("test", "p1") is not None

    def test_feedback_persists(self, tmp_path):
        store_dir = tmp_path / "data"
        store = MemoryStore(data_dir=store_dir)

        fb = UserFeedback(agent="test", alert_type="alert", feedback="useful", context={})
        store.record_feedback(fb)

        store2 = MemoryStore(data_dir=store_dir)
        assert len(store2._feedback) == 1
        assert store2._feedback[0].feedback == "useful"

    def test_feedback_roundtrip_with_timestamp(self, tmp_path):
        """Regression test: _load_feedback must handle ISO timestamp strings."""
        store_dir = tmp_path / "data"
        store = MemoryStore(data_dir=store_dir)

        fb = UserFeedback(agent="test", alert_type="alert", feedback="useful", context={"k": "v"})
        store.record_feedback(fb)

        # Verify the stored JSON has a string timestamp
        data = json.loads(store._feedback_file.read_text())
        assert isinstance(data[0]["timestamp"], str)

        # Reload should not crash (the bug was UserFeedback(**f) with string timestamp)
        store2 = MemoryStore(data_dir=store_dir)
        assert isinstance(store2._feedback[0].timestamp, datetime)


class TestBaselineWelford:
    def test_single_sample(self, memory_store):
        obs = Observation(agent="a", metric="m", value=10.0)
        memory_store.record_observation(obs)

        bl = memory_store.get_baseline("a", "m")
        assert bl is not None
        assert bl.mean == 10.0
        assert bl.std_dev == 0.0
        assert bl.sample_count == 1
        assert bl.min_value == 10.0
        assert bl.max_value == 10.0

    def test_two_samples(self, memory_store):
        for v in [10.0, 20.0]:
            memory_store.record_observation(
                Observation(agent="a", metric="m", value=v)
            )
        bl = memory_store.get_baseline("a", "m")
        assert bl.mean == pytest.approx(15.0)
        assert bl.sample_count == 2
        assert bl.min_value == 10.0
        assert bl.max_value == 20.0

    def test_fifteen_samples(self, memory_store):
        values = [10.0, 12.0, 14.0, 11.0, 13.0, 15.0, 10.5, 12.5, 14.5, 11.5,
                  13.5, 15.5, 10.0, 12.0, 14.0]
        seed_observations(memory_store, "a", "m", values)

        bl = memory_store.get_baseline("a", "m")
        assert bl.sample_count == 15

        import statistics
        expected_mean = statistics.mean(values)
        expected_std = statistics.pstdev(values)  # population std_dev (Welford's gives population)

        assert bl.mean == pytest.approx(expected_mean, abs=0.01)
        assert bl.std_dev == pytest.approx(expected_std, abs=0.01)

    def test_non_numeric_observation_no_baseline(self, memory_store):
        obs = Observation(agent="a", metric="m", value="text")
        memory_store.record_observation(obs)
        assert memory_store.get_baseline("a", "m") is None


class TestIsAnomaly:
    def test_insufficient_data(self, memory_store):
        # Less than 10 samples -> never anomaly
        for v in [50.0] * 5:
            memory_store.record_observation(
                Observation(agent="a", metric="m", value=v)
            )
        assert memory_store.is_anomaly("a", "m", 100.0) is False

    def test_normal_value(self, memory_store):
        seed_observations(memory_store, "a", "m", [50.0] * 15)
        # All same values -> std_dev=0 -> exact match is not anomaly
        assert memory_store.is_anomaly("a", "m", 50.0) is False

    def test_extreme_value(self, memory_store):
        values = [50.0 + i * 0.1 for i in range(15)]  # 50.0..51.4
        seed_observations(memory_store, "a", "m", values)
        # A value far away should be anomaly
        assert memory_store.is_anomaly("a", "m", 100.0) is True

    def test_no_baseline(self, memory_store):
        assert memory_store.is_anomaly("a", "nonexistent", 99.0) is False


class TestGetObservations:
    def test_filter_by_agent_metric(self, memory_store):
        memory_store.record_observation(Observation(agent="a", metric="m1", value=1))
        memory_store.record_observation(Observation(agent="a", metric="m2", value=2))
        memory_store.record_observation(Observation(agent="b", metric="m1", value=3))

        results = memory_store.get_observations("a", "m1")
        assert len(results) == 1
        assert results[0].value == 1

    def test_filter_by_since(self, memory_store):
        old = Observation(agent="a", metric="m", value=1,
                          timestamp=datetime.now() - timedelta(days=5))
        new = Observation(agent="a", metric="m", value=2,
                          timestamp=datetime.now())
        memory_store._observations.extend([old, new])

        since = datetime.now() - timedelta(days=1)
        results = memory_store.get_observations("a", "m", since=since)
        assert len(results) == 1
        assert results[0].value == 2

    def test_sorted_by_timestamp(self, memory_store):
        now = datetime.now()
        obs1 = Observation(agent="a", metric="m", value=1,
                           timestamp=now - timedelta(hours=2))
        obs2 = Observation(agent="a", metric="m", value=2,
                           timestamp=now - timedelta(hours=1))
        obs3 = Observation(agent="a", metric="m", value=3,
                           timestamp=now)
        # Insert out of order
        memory_store._observations.extend([obs3, obs1, obs2])

        results = memory_store.get_observations("a", "m")
        assert [o.value for o in results] == [1, 2, 3]


class TestRollingWindow:
    def test_old_observations_removed(self, tmp_path):
        store = MemoryStore(data_dir=tmp_path / "data")

        old_obs = Observation(agent="a", metric="m", value=1,
                              timestamp=datetime.now() - timedelta(days=45))
        store._observations.append(old_obs)
        store._save_observations()

        # After save, old observation should be gone
        assert len(store._observations) == 0

    def test_recent_observations_kept(self, tmp_path):
        store = MemoryStore(data_dir=tmp_path / "data")

        recent = Observation(agent="a", metric="m", value=1,
                             timestamp=datetime.now() - timedelta(days=5))
        store._observations.append(recent)
        store._save_observations()

        assert len(store._observations) == 1


class TestPatterns:
    def test_add_and_get(self, memory_store):
        p = Pattern(agent="a", name="p1", description="d",
                     condition={}, action="ignore", confidence=0.8)
        memory_store.add_pattern(p)

        assert memory_store.get_pattern("a", "p1") is not None
        assert memory_store.get_pattern("a", "nonexistent") is None

    def test_get_patterns_by_agent(self, memory_store):
        memory_store.add_pattern(
            Pattern(agent="a", name="p1", description="d",
                     condition={}, action="ignore", confidence=0.8))
        memory_store.add_pattern(
            Pattern(agent="b", name="p2", description="d",
                     condition={}, action="ignore", confidence=0.8))

        assert len(memory_store.get_patterns("a")) == 1
        assert len(memory_store.get_patterns("b")) == 1

    def test_trigger_increments_count(self, memory_store):
        p = Pattern(agent="a", name="p1", description="d",
                     condition={}, action="ignore", confidence=0.8, occurrences=0)
        memory_store.add_pattern(p)

        memory_store.trigger_pattern("a", "p1")
        stored = memory_store.get_pattern("a", "p1")
        assert stored.occurrences == 1
        assert stored.last_triggered is not None

    def test_trigger_nonexistent_noop(self, memory_store):
        memory_store.trigger_pattern("a", "nonexistent")  # Should not raise


class TestFeedback:
    def test_record_and_retrieve(self, memory_store):
        fb = UserFeedback(agent="a", alert_type="alert", feedback="useful", context={})
        memory_store.record_feedback(fb)
        assert len(memory_store._feedback) == 1

    def test_false_positive_creates_pattern(self, memory_store):
        fb = UserFeedback(
            agent="a", alert_type="storage_warning",
            feedback="false_positive", context={"volume": "V1"},
        )
        memory_store.record_feedback(fb)

        p = memory_store.get_pattern("a", "suppress_storage_warning")
        assert p is not None
        assert p.action == "ignore"
        assert p.confidence == 0.5

    def test_false_positive_reinforces_existing(self, memory_store):
        # First false positive
        fb1 = UserFeedback(
            agent="a", alert_type="warn",
            feedback="false_positive", context={"k": "v"},
        )
        memory_store.record_feedback(fb1)

        initial_conf = memory_store.get_pattern("a", "suppress_warn").confidence

        # Second false positive
        fb2 = UserFeedback(
            agent="a", alert_type="warn",
            feedback="false_positive", context={"k": "v"},
        )
        memory_store.record_feedback(fb2)

        p = memory_store.get_pattern("a", "suppress_warn")
        assert p.confidence > initial_conf
        assert p.occurrences == 2

    def test_useful_feedback_no_pattern(self, memory_store):
        fb = UserFeedback(
            agent="a", alert_type="alert",
            feedback="useful", context={},
        )
        memory_store.record_feedback(fb)
        assert memory_store.get_pattern("a", "suppress_alert") is None


class TestFalsePositiveRate:
    def test_no_feedback_returns_zero(self, memory_store):
        assert memory_store.get_false_positive_rate("a", "alert") == 0.0

    def test_mixed_feedback(self, memory_store):
        # 2 false positives, 3 useful = 40% FP rate
        for _ in range(2):
            memory_store.record_feedback(
                UserFeedback(agent="a", alert_type="alert",
                             feedback="false_positive", context={}))
        for _ in range(3):
            memory_store.record_feedback(
                UserFeedback(agent="a", alert_type="alert",
                             feedback="useful", context={}))

        assert memory_store.get_false_positive_rate("a", "alert") == pytest.approx(0.4)


class TestGetTrend:
    def test_increasing(self, memory_store):
        # First half ~10, second half ~20 -> >10% increase
        values = [10, 10, 10, 10, 10, 20, 20, 20, 20, 20]
        seed_observations(memory_store, "a", "m", values)
        assert memory_store.get_trend("a", "m") == "increasing"

    def test_decreasing(self, memory_store):
        values = [20, 20, 20, 20, 20, 10, 10, 10, 10, 10]
        seed_observations(memory_store, "a", "m", values)
        assert memory_store.get_trend("a", "m") == "decreasing"

    def test_stable(self, memory_store):
        values = [50, 50, 50, 50, 50, 51, 50, 51, 50, 51]
        seed_observations(memory_store, "a", "m", values)
        assert memory_store.get_trend("a", "m") == "stable"

    def test_insufficient_data(self, memory_store):
        seed_observations(memory_store, "a", "m", [50])
        assert memory_store.get_trend("a", "m") == "unknown"

    def test_no_data(self, memory_store):
        assert memory_store.get_trend("a", "m") == "unknown"


class TestGetInsights:
    def test_correct_counts(self, memory_store):
        seed_observations(memory_store, "a", "m1", [10, 20])
        seed_observations(memory_store, "a", "m2", [30, 40])

        p1 = Pattern(agent="a", name="p1", description="d",
                      condition={}, action="ignore", confidence=0.8)
        p2 = Pattern(agent="a", name="p2", description="d",
                      condition={}, action="ignore", confidence=0.5)
        memory_store.add_pattern(p1)
        memory_store.add_pattern(p2)

        insights = memory_store.get_insights("a")

        assert insights["baselines_learned"] == 2
        assert insights["patterns_learned"] == 2
        assert insights["active_patterns"] == 1  # only p1 has confidence >= 0.7
        assert insights["total_observations"] == 4
