from ariano_api import security


def test_password_hash_is_salted_and_verifiable():
    first = security.hash_password("senha-longa-de-teste")
    second = security.hash_password("senha-longa-de-teste")
    assert first != second
    assert security.verify_password("senha-longa-de-teste", first)
    assert not security.verify_password("senha-incorreta", first)
    assert not security.verify_password("senha-longa-de-teste", "formato-invalido")


def test_session_token_is_random_and_only_its_digest_is_persisted():
    first = security.new_token()
    second = security.new_token()
    assert first != second
    assert len(security.token_hash(first)) == 64
    assert security.token_hash(first) != security.token_hash(second)

