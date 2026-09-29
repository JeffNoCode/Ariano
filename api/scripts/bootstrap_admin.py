"""Create a local administrator from an interactive or piped password."""

from __future__ import annotations

import argparse
import getpass
import sys

import psycopg

from ariano_api import auth_repository, db, security


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an ARIANO administrator")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Administrador ARIANO")
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass("Senha: ")
    if len(password) < 12:
        parser.error("a senha deve ter pelo menos 12 caracteres")
    db.open_pool()
    try:
        with db.connection() as conn:
            existing = auth_repository.user_by_email(conn, args.email.strip().lower())
            if existing is not None:
                if existing["role"] != "ADMIN" or not security.verify_password(password, existing["password_hash"]):
                    parser.error("conta existente sem perfil ADMIN ou senha incorreta")
                print(f"Administrador existente confirmado: id={existing['id']} email={existing['email']}")
                return
            user = auth_repository.create_user(
                conn, args.name.strip(), args.email.strip().lower(),
                security.hash_password(password), "ADMIN",
            )
        print(f"Administrador criado: id={user['id']} email={user['email']}")
    except psycopg.errors.UniqueViolation:
        parser.error("email já cadastrado")
    finally:
        db.close_pool()


if __name__ == "__main__":
    main()

