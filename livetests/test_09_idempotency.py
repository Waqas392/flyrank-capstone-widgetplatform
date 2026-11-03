"""A retried submission (same Idempotency-Key) is stored exactly once."""
import uuid

from conftest import dash_items, expect, submit


def test_same_key_stores_once(http, hA, wA):
    """Two POSTs with the same Idempotency-Key -> 201 then 200 duplicate, same id, one row"""
    key = f"live-{uuid.uuid4()}"
    first = expect(submit(http, wA["id"], headers={"Idempotency-Key": key}), 201).json()
    second = expect(submit(http, wA["id"], headers={"Idempotency-Key": key}), 200).json()
    assert first["id"] == second["id"] and second["duplicate"] is True
    assert len(dash_items(http, hA, wA["id"])) == 1, "retry created a second row"


def test_different_keys_store_separately(http, hA, wA):
    """Different Idempotency-Keys -> two rows"""
    expect(submit(http, wA["id"], headers={"Idempotency-Key": f"a-{uuid.uuid4()}"}), 201)
    expect(submit(http, wA["id"], headers={"Idempotency-Key": f"b-{uuid.uuid4()}"}), 201)
    assert len(dash_items(http, hA, wA["id"])) == 2


def test_same_key_on_different_widgets_is_independent(http, hA, make_widget):
    """The same key used on two different widgets is not treated as a duplicate"""
    key = f"shared-{uuid.uuid4()}"
    w1, w2 = make_widget(hA), make_widget(hA)
    expect(submit(http, w1["id"], headers={"Idempotency-Key": key}), 201)
    expect(submit(http, w2["id"], headers={"Idempotency-Key": key}), 201)
