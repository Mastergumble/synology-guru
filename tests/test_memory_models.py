"""Tests for memory data models."""

from datetime import datetime

import pytest

from src.memory.models import Baseline, Observation, Pattern, UserFeedback


class TestObservation:
    def test_roundtrip(self):
        obs = Observation(agent="storage", metric="usage", value=75.5, context={"vol": "V1"})
        d = obs.to_dict()
        restored = Observation.from_dict(d)

        assert restored.agent == obs.agent
        assert restored.metric == obs.metric
        assert restored.value == obs.value
        assert restored.context == obs.context
        assert isinstance(restored.timestamp, datetime)

    def test_default_timestamp(self):
        obs = Observation(agent="a", metric="m", value=1)
        assert isinstance(obs.timestamp, datetime)

    def test_default_context_empty(self):
        obs = Observation(agent="a", metric="m", value=1)
        assert obs.context == {}


class TestBaseline:
    def test_roundtrip(self):
        bl = Baseline(
            agent="storage",
            metric="usage",
            mean=50.0,
            std_dev=5.0,
            min_value=30.0,
            max_value=70.0,
            sample_count=20,
        )
        d = bl.to_dict()
        restored = Baseline.from_dict(d)

        assert restored.agent == bl.agent
        assert restored.mean == bl.mean
        assert restored.std_dev == bl.std_dev
        assert restored.min_value == bl.min_value
        assert restored.max_value == bl.max_value
        assert restored.sample_count == bl.sample_count

    def test_is_anomaly_normal(self):
        bl = Baseline(agent="a", metric="m", mean=50.0, std_dev=5.0,
                      min_value=30, max_value=70, sample_count=20)
        assert bl.is_anomaly(55.0) is False  # 1 std_dev away

    def test_is_anomaly_extreme(self):
        bl = Baseline(agent="a", metric="m", mean=50.0, std_dev=5.0,
                      min_value=30, max_value=70, sample_count=20)
        assert bl.is_anomaly(65.0) is True  # 3 std_dev away

    def test_is_anomaly_zero_std_same_value(self):
        bl = Baseline(agent="a", metric="m", mean=50.0, std_dev=0.0,
                      min_value=50, max_value=50, sample_count=5)
        assert bl.is_anomaly(50.0) is False

    def test_is_anomaly_zero_std_different_value(self):
        bl = Baseline(agent="a", metric="m", mean=50.0, std_dev=0.0,
                      min_value=50, max_value=50, sample_count=5)
        assert bl.is_anomaly(51.0) is True

    def test_is_anomaly_boundary(self):
        bl = Baseline(agent="a", metric="m", mean=50.0, std_dev=5.0,
                      min_value=30, max_value=70, sample_count=20)
        # Exactly at 2 std_dev boundary (z-score = 2.0, sensitivity = 2.0) -> not anomaly (> not >=)
        assert bl.is_anomaly(60.0, sensitivity=2.0) is False

    def test_is_anomaly_custom_sensitivity(self):
        bl = Baseline(agent="a", metric="m", mean=50.0, std_dev=5.0,
                      min_value=30, max_value=70, sample_count=20)
        # z=1.2 with sensitivity=1.0 -> anomaly
        assert bl.is_anomaly(56.0, sensitivity=1.0) is True


class TestPattern:
    def test_roundtrip(self):
        p = Pattern(
            agent="storage",
            name="suppress_high",
            description="Suppress high alerts",
            condition={"volume": "V1"},
            action="ignore",
            confidence=0.8,
            occurrences=3,
        )
        d = p.to_dict()
        restored = Pattern.from_dict(d)

        assert restored.agent == p.agent
        assert restored.name == p.name
        assert restored.condition == p.condition
        assert restored.confidence == p.confidence
        assert restored.occurrences == 3

    def test_without_last_triggered(self):
        p = Pattern(
            agent="a", name="n", description="d",
            condition={}, action="ignore", confidence=0.5,
        )
        d = p.to_dict()
        assert d["last_triggered"] is None
        restored = Pattern.from_dict(d)
        assert restored.last_triggered is None

    def test_with_last_triggered(self):
        now = datetime.now()
        p = Pattern(
            agent="a", name="n", description="d",
            condition={}, action="ignore", confidence=0.5,
            last_triggered=now,
        )
        d = p.to_dict()
        restored = Pattern.from_dict(d)
        assert isinstance(restored.last_triggered, datetime)


class TestUserFeedback:
    def test_to_dict(self):
        fb = UserFeedback(
            agent="storage",
            alert_type="storage_warning",
            feedback="false_positive",
            context={"volume": "V1"},
        )
        d = fb.to_dict()

        assert d["agent"] == "storage"
        assert d["feedback"] == "false_positive"
        assert isinstance(d["timestamp"], str)

    def test_roundtrip(self):
        fb = UserFeedback(
            agent="storage",
            alert_type="storage_warning",
            feedback="useful",
            context={"volume": "V1"},
        )
        d = fb.to_dict()
        restored = UserFeedback.from_dict(d)

        assert restored.agent == fb.agent
        assert restored.alert_type == fb.alert_type
        assert restored.feedback == fb.feedback
        assert restored.context == fb.context
        assert isinstance(restored.timestamp, datetime)
