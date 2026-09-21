"""Admin commands. Run from the backend folder:

    python -m app.manage stats                 # row counts per table
    python -m app.manage reset --yes           # delete ALL data (SQLite or Postgres) and recreate empty tables
    python -m app.manage reset-chats --yes     # delete only assistant chat history
    python -m app.manage reset-demo --yes      # restore the shared demo account to its original data
    python -m app.manage admins                # show which emails have admin access (ADMIN_EMAILS)
"""
import sys
from sqlalchemy import inspect, text
from .db import Base, engine, init_db, SessionLocal, ChatMessage, DB_URL


def stats():
    insp = inspect(engine)
    print(f"Database: {'PostgreSQL' if not DB_URL.startswith('sqlite') else DB_URL}")
    with engine.connect() as c:
        for t in sorted(insp.get_table_names()):
            print(f"  {t:16s} {c.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar():>8,}")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "help"
    sure = "--yes" in argv
    if cmd == "stats":
        stats()
    elif cmd == "reset":
        if not sure:
            print("This deletes EVERY user, transaction, budget, goal and chat. Re-run with --yes to confirm.")
            return 1
        Base.metadata.drop_all(engine)
        init_db()
        print("All data deleted. Tables recreated empty. The demo account is recreated when the server next starts.")
    elif cmd == "reset-chats":
        if not sure:
            print("Re-run with --yes to delete all assistant chat history.")
            return 1
        db = SessionLocal()
        n = db.query(ChatMessage).delete()
        db.commit()
        db.close()
        print(f"Deleted {n} chat messages.")
    elif cmd == "reset-demo":
        if not sure:
            print("Re-run with --yes to restore the demo account's original data.")
            return 1
        from .db import User, Transaction, Budget, Goal, LoginEvent
        from .seed import DEMO_EMAIL, ensure_demo
        db = SessionLocal()
        u = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if u:
            for model in (Transaction, Budget, Goal, ChatMessage, LoginEvent):
                db.query(model).filter(model.user_id == u.id).delete()
            db.delete(u)
            db.commit()
        from .ml.categorizer import categorizer
        from .services import training_corrections
        categorizer.train(training_corrections(db))
        ensure_demo(db)
        db.close()
        print("Demo account restored to its original 6 months of data.")
    elif cmd == "admins":
        from .auth import admin_emails
        a = admin_emails()
        print("Admins: " + (", ".join(sorted(a)) if a else "none. Set ADMIN_EMAILS in backend/.env (or Render's environment)."))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
