import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def ensure_development_key_pair(
    private_directory: Path,
    *,
    public_directory: Path | None = None,
) -> tuple[Path, Path]:
    public_directory = public_directory or private_directory
    private_directory.mkdir(parents=True, exist_ok=True)
    public_directory.mkdir(parents=True, exist_ok=True)
    private_key_file = private_directory / "private.pem"
    public_key_file = public_directory / "public.pem"
    existing = (private_key_file.exists(), public_key_file.exists())
    if existing == (True, True):
        return private_key_file, public_key_file
    if any(existing):
        raise RuntimeError("development JWT key volume contains a partial key pair")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_file.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    private_key_file.chmod(0o600)
    public_key_file.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    public_key_file.chmod(0o644)
    return private_key_file, public_key_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Create local internal JWT keys")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--public-directory", type=Path)
    args = parser.parse_args()
    ensure_development_key_pair(
        args.directory,
        public_directory=args.public_directory,
    )


if __name__ == "__main__":
    main()


__all__ = ["ensure_development_key_pair", "main"]
