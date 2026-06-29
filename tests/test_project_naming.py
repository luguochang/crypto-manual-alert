from pathlib import Path


def test_public_package_name_is_crypto_manual_alert():
    """The public repo should not expose the old internal package name."""

    import crypto_manual_alert

    assert crypto_manual_alert.__name__ == "crypto_manual_alert"
    assert Path("src/crypto_manual_alert").is_dir()
    old_package = "_".join(("jia" + "mi", "crypto", "alert"))
    assert not (Path("src") / old_package).exists()
