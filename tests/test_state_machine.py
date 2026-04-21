from core.state_machine import StateMachine, State


def test_initial_state_is_idle():
    sm = StateMachine()
    assert sm.state == State.IDLE


def test_idle_to_guiding_on_customer_approach():
    sm = StateMachine()
    assert sm.trigger("customer_approach") is True
    assert sm.state == State.GUIDING


def test_guiding_to_cooking_on_bowl_placed():
    sm = StateMachine()
    sm.trigger("customer_approach")
    assert sm.trigger("bowl_placed") is True
    assert sm.state == State.COOKING


def test_cooking_to_waiting_on_meal_ready():
    sm = StateMachine()
    sm.trigger("customer_approach")
    sm.trigger("bowl_placed")
    assert sm.trigger("meal_ready") is True
    assert sm.state == State.WAITING


def test_waiting_to_idle_on_bowl_removed():
    sm = StateMachine()
    sm.trigger("customer_approach")
    sm.trigger("bowl_placed")
    sm.trigger("meal_ready")
    assert sm.trigger("bowl_removed") is True
    assert sm.state == State.IDLE


def test_invalid_transition_is_rejected():
    sm = StateMachine()
    assert sm.trigger("bowl_placed") is False
    assert sm.state == State.IDLE


def test_event_handler_is_called():
    sm = StateMachine()
    called = []
    sm.on("customer_approach", lambda old, new, ctx: called.append((old, new)))
    sm.trigger("customer_approach")
    assert len(called) == 1
    assert called[0][1] == State.GUIDING
