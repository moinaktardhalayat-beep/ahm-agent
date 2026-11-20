"""CLI to manage dashboard users (Local & MySQL)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import auth
import data

def cmd_add(args):
    if data.get_user(args.username):
        print(f"ERROR: user '{args.username}' already exists")
        return 1
        
    role = "admin" if args.admin else "member"
    pw_hash = auth.hash_password(args.password)
    display = args.display or args.username
    
    user_data = {
        "username": args.username,
        "display_name": display,
        "role": role,
        "password_hash": pw_hash
    }
    data.save_user(user_data)
    print(f"Added user '{args.username}'.")
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

def cmd_reset(args):
    user = data.get_user(args.username)
    if not user:
        print(f"ERROR: user '{args.username}' not found")
        return 1
    user["password_hash"] = auth.hash_password(args.password)
    data.save_user(user)
    print(f"Password reset for '{args.username}'")
    return 0

def cmd_delete(args):
    users = data.get_users()
    user = next((u for u in users if u["username"] == args.username), None)
    if not user:
        print(f"ERROR: user '{args.username}' not found")
        return 1
    if user.get("role") == "admin":
        admins = [u for u in users if u.get("role") == "admin"]
        if len(admins) <= 1:
            print("ERROR: cannot delete the last admin")
            return 1
    data.delete_user(args.username)
    print(f"Deleted '{args.username}'")
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

    p_reset = sub.add_parser("reset")
    p_reset.add_argument("username")
    p_reset.add_argument("password")
    p_reset.set_defaults(func=cmd_reset)

    p_del = sub.add_parser("delete")
    p_del.add_argument("username")
    p_del.set_defaults(func=cmd_delete)

    args = p.parse_args()
    sys.exit(args.func(args))

if __name__ == "__main__":
    main()