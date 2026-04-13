#!/usr/bin/env python3
"""CLI for database management."""
import argparse
import getpass
import os
import sys

import bcrypt
from dotenv import load_dotenv

load_dotenv()


def cmd_init_db(args):
    from storage.database import init_db
    path = args.workspace or os.getenv("WORKSPACE", "workspaces/imoveis.db")
    if path != ":memory:" and os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    init_db(path)
    print(f"Database initialized: {path}")


def cmd_create_user(args):
    from storage.database import init_db, get_connection, create_user, get_user_by_username
    path = args.workspace or os.getenv("WORKSPACE", "workspaces/imoveis.db")
    init_db(path)
    conn = get_connection(path)
    username = input("Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)
    if get_user_by_username(conn, username):
        print(f"User '{username}' already exists.")
        conn.close()
        sys.exit(1)
    password = getpass.getpass("Password: ")
    if not password:
        print("Password cannot be empty.")
        sys.exit(1)
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    create_user(conn, username, pw_hash)
    conn.commit()
    conn.close()
    print(f"User '{username}' created successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Imoveis DI management CLI")
    parser.add_argument("--workspace", default=None, help="Path to SQLite workspace file")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("init-db", help="Initialize the database schema")
    sub.add_parser("create-user", help="Create a new user")
    args = parser.parse_args()
    if args.command == "init-db":
        cmd_init_db(args)
    elif args.command == "create-user":
        cmd_create_user(args)
    else:
        parser.print_help()
