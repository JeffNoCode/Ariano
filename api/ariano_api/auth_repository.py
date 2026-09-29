"""PostgreSQL operations for accounts and bearer sessions."""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection


def create_user(conn: Connection, name: str, email: str, password_hash: str, role: str = "VIEWER") -> dict:
    return conn.execute(
        """INSERT INTO tb_users (name, email, password_hash, role)
           VALUES (%s, %s, %s, %s)
           RETURNING id, name, email, role, is_active, created_at""",
        (name, email.lower(), password_hash, role),
    ).fetchone()


def user_by_email(conn: Connection, email: str) -> dict | None:
    return conn.execute(
        "SELECT id, name, email, password_hash, role, is_active FROM tb_users WHERE lower(email) = %s",
        (email.lower(),),
    ).fetchone()


def user_by_session(conn: Connection, digest: str) -> dict | None:
    return conn.execute(
        """SELECT u.id, u.name, u.email, u.role, u.is_active, u.created_at
             FROM tb_sessions s JOIN tb_users u ON u.id = s.user_id
            WHERE s.token_hash = %s AND s.expires_at > now()
              AND s.revoked_at IS NULL AND u.is_active""",
        (digest,),
    ).fetchone()


def create_session(conn: Connection, digest: str, user_id: int, expires_at: datetime) -> None:
    conn.execute(
        "INSERT INTO tb_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (digest, user_id, expires_at),
    )


def revoke_session(conn: Connection, digest: str) -> None:
    conn.execute("UPDATE tb_sessions SET revoked_at = now() WHERE token_hash = %s", (digest,))


def list_users(conn: Connection) -> list[dict]:
    return conn.execute(
        "SELECT id, name, email, role, is_active, created_at FROM tb_users ORDER BY id"
    ).fetchall()


def set_role(conn: Connection, user_id: int, role: str) -> dict | None:
    return conn.execute(
        """UPDATE tb_users SET role = %s, updated_at = now() WHERE id = %s
           RETURNING id, name, email, role, is_active, created_at""",
        (role, user_id),
    ).fetchone()


def admin_count(conn: Connection) -> int:
    return conn.execute("SELECT count(*) AS count FROM tb_users WHERE role = 'ADMIN' AND is_active").fetchone()["count"]

