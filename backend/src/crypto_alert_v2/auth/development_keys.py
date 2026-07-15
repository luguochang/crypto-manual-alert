import argparse
from pathlib import Path
from secrets import token_urlsafe

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


def ensure_development_cursor_key(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    key_file = directory / "key"
    if key_file.exists():
        if not key_file.read_text().strip():
            raise RuntimeError("development Product Inbox cursor key is empty")
        key_file.chmod(0o600)
        return key_file

    key_file.write_text(token_urlsafe(32))
    key_file.chmod(0o600)
    return key_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Create local internal JWT keys")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--public-directory", type=Path)
    parser.add_argument("--cursor-key-directory", type=Path)
    args = parser.parse_args()
    ensure_development_key_pair(
        args.directory,
        public_directory=args.public_directory,
    )
    if args.cursor_key_directory is not None:
        ensure_development_cursor_key(args.cursor_key_directory)


if __name__ == "__main__":
    main()


__all__ = ["ensure_development_cursor_key", "ensure_development_key_pair", "main"]
