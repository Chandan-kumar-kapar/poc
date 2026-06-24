#!/usr/bin/env python3
"""Generate an RS256 keypair for JWT signing.

Writes:
  secrets/jwt_private.pem        (PKCS8 private key — KEEP SECRET)
  secrets/jwks/<kid>.pem         (public key, named by kid)

Usage:
  python scripts/generate_keys.py --kid poc-key-a --out secrets
"""
from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kid", default="poc-key-a", help="Key ID for the public key")
    parser.add_argument("--out", default="secrets", help="Output directory")
    parser.add_argument("--bits", type=int, default=2048, help="RSA key size")
    args = parser.parse_args()

    out = Path(args.out)
    jwks_dir = out / "jwks"
    jwks_dir.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=args.bits)

    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    priv_path = out / "jwt_private.pem"
    pub_path = jwks_dir / f"{args.kid}.pem"
    priv_path.write_bytes(private_pem)
    pub_path.write_bytes(public_pem)

    # Lock down the private key.
    try:
        priv_path.chmod(0o600)
    except OSError:
        pass

    print(f"Wrote private key:  {priv_path}")
    print(f"Wrote public key:   {pub_path}")
    print(f"Active kid:         {args.kid}")
    print("\nSet in your environment:")
    print(f"  JWT_PRIVATE_KEY_PATH={priv_path}")
    print(f"  JWT_PUBLIC_KEYS_PATH={jwks_dir}/")
    print(f"  JWT_ACTIVE_KID={args.kid}")


if __name__ == "__main__":
    main()
