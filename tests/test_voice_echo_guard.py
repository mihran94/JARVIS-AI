"""Echo suppression is local, bounded and never blocks unrelated speech."""
from voice.echo_guard import EchoGuard


def test_recent_long_spoken_reply_is_filtered_only_during_echo_window():
    clock = [100.0]
    guard = EchoGuard(window_seconds=2.5, clock=lambda: clock[0])
    guard.record('JARVIS is preparing your requested website now.')
    assert guard.is_echo('JARVIS is preparing your requested website now')
    assert guard.is_echo('preparing your requested website')
    assert not guard.is_echo('open the calculator')
    clock[0] = 103.0
    assert not guard.is_echo('JARVIS is preparing your requested website now')


def test_reset_and_short_commands_are_not_swallowed():
    guard = EchoGuard(clock=lambda: 50.0)
    guard.record('Hey Jarvis open the calculator')
    assert not guard.is_echo('Hey Jarvis')
    guard.reset()
    assert not guard.is_echo('Hey Jarvis open the calculator')
