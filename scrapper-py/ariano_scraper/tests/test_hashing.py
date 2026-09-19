from utils.hashing import sha256_of_file


def test_hash_is_deterministic(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_bytes(b"conteudo identico")

    hash_1 = sha256_of_file(file_path)
    hash_2 = sha256_of_file(file_path)

    assert hash_1 == hash_2
    assert hash_1.startswith("sha256:")


def test_hash_differs_for_different_content(tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_bytes(b"conteudo A")
    file_b.write_bytes(b"conteudo B")

    assert sha256_of_file(file_a) != sha256_of_file(file_b)


def test_hash_matches_hashlib_reference(tmp_path):

    import hashlib

    file_path = tmp_path / "known.txt"
    content = b"ariano"
    file_path.write_bytes(content)

    expected = "sha256:" + hashlib.sha256(content).hexdigest()
    assert sha256_of_file(file_path) == expected
