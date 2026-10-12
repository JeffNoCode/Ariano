"""Local Docker operator recovery; never exposed as an HTTP endpoint."""

from __future__ import annotations

import argparse
import os
import sys

from ariano_api import db, security


def main() -> None:
    parser = argparse.ArgumentParser(description="Redefinir uma senha ADMIN no ambiente local")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password-stdin", action="store_true", required=True)
    args = parser.parse_args()
    if os.environ.get("ARIANO_LOCAL_PASSWORD_RESET") != "yes":
        parser.error("redefinição local não habilitada")
    password = sys.stdin.readline().rstrip("\r\n")
    if len(password) < 12:
        parser.error("a nova senha precisa ter pelo menos 12 caracteres")
    email = args.email.strip().lower()
    db.open_pool()
    try:
        with db.connection() as conn:
            user = conn.execute(
                "SELECT id, email FROM tb_users WHERE lower(email) = %s AND role = 'ADMIN' AND is_active FOR UPDATE",
                (email,),
            ).fetchone()
            if user is None:
                parser.error("não existe uma conta ADMIN ativa com esse e-mail")
            conn.execute(
                "UPDATE tb_users SET password_hash = %s, updated_at = now() WHERE id = %s",
                (security.hash_password(password), user["id"]),
            )
            conn.execute(
                "UPDATE tb_sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL",
                (user["id"],),
            )
        print(f"Senha redefinida e sessões anteriores encerradas: {user['email']}")
    finally:
        db.close_pool()


if __name__ == "__main__":
    main()

