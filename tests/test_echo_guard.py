from voice.audio.echo_guard import EchoGuard

SPOKEN = (
    "Your portfolio is worth ₹20,000 today. Your total P&L is up 3.5 percent, "
    "and your largest holding is Reliance Industries."
)


def guard():
    g = EchoGuard()
    g.note_spoken(SPOKEN, now=0.0)
    return g


def test_exact_and_partial_echo_is_detected():
    g = guard()
    assert g.is_echo("Your portfolio is worth", now=1)
    assert g.is_echo("largest holding is Reliance", now=1)


def test_asr_variants_are_detected():
    g = guard()
    assert g.is_echo("port folio is worth twenty thousand rupees", now=1)
    assert g.is_echo("your total P and L is up", now=1)


def test_real_interruptions_are_not_echo():
    g = guard()
    assert not g.is_echo("stop", now=1)
    assert not g.is_echo("what about TCS", now=1)
    assert not g.is_echo("wait show me infosys news", now=1)


def test_fillers_and_empty_are_ignored():
    g = guard()
    assert g.is_echo("hmm", now=1)
    assert g.is_echo("", now=1)


def test_nothing_spoken_means_not_echo():
    assert not EchoGuard().is_echo("what is my balance", now=1)


def test_old_text_expires_and_clear_works():
    g = guard()
    assert not g.is_echo("your portfolio is worth", now=100)
    g.note_spoken(SPOKEN, now=100)
    g.clear()
    assert not g.is_echo("your portfolio is worth", now=101)
