"""CLI to manage dashboard users in MySQL."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import auth
import data

def cmd_add(args):
    with data.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE username=%s", (args.username,))
            if cur.fetchone():
                print(f"ERROR: user '{args.username}' already exists")
                return 1
            
            role = "admin" if args.admin else "member"
            pw_hash = auth.hash_password(args.password)
            display = args.display or args.username
            
            cur.execute(
                "INSERT INTO users (username, display_name, role, password_hash) VALUES (%s, %s, %s, %s)",
                (args.username, display, role, pw_hash)
            )
    print(f"Added user '{args.username}' to MySQL database.")
    return 0

def cmd_list(_args):
    users = data.get_users()
    if not users:
        print("No users found.")
        return 0
    print(f"{'username':<20} {'role':<8} {'display_name':<30}")
    print("-" * 60)
    for u in users:
        print(f"{u['username']:<20} {u.get('role', 'member'):<8} {u.get('display_name', ''):<30}")
    return 0

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("username")
    p_add.add_argument("password")
    p_add.add_argument("--admin", action="store_true")
    p_add.add_argument("--display", default="")
    p_add.set_defaults(func=cmd_add)

    sub.add_parser("list").set_defaults(func=cmd_list)

    args = p.parse_args()
    sys.exit(args.func(args))

if __name__ == "__main__":
    main()