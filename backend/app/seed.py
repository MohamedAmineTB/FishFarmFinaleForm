"""Create the public demo farm: `python -m app.seed` (add `--reset` to start from an empty database).

Owner nadia@lacvert.farm, workers karim/lea/ines@lacvert.farm, technician samir@lacvert.farm,
all with the password demo1234.
"""

import sys
import time

from sqlalchemy import select, text

from .db import session_scope
from .models import User
from .services.demo import load_demo
from .services.farm import create_owner

DEMO_OWNER = "nadia@lacvert.farm"


def main(reset: bool = False) -> None:
    t0 = time.time()
    with session_scope() as db:
        existing = db.scalar(select(User).where(User.email == DEMO_OWNER))
        if existing and not reset:
            print("Demo farm already exists (use --reset to rebuild it).")
            return
        if existing:
            # deleting the owner cascades to the whole farm
            team = db.execute(text("SELECT user_id FROM user_roles WHERE owner_user_id = :o AND user_id <> :o"),
                              {"o": existing.id}).scalars().all()
            for uid in team:
                db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
            for t in ("readings", "alerts", "reports", "tasks", "maintenance", "predictions", "hourly_stats"):
                db.execute(text(f"DELETE FROM {t} WHERE owner_user_id = :o"), {"o": existing.id})
            db.execute(text("DELETE FROM users WHERE id = :u"), {"u": existing.id})
            db.flush()
        owner = create_owner(db, name="Nadia Amrani", email=DEMO_OWNER, password="demo1234", farm_name="Lac Vert",
                             company="Lac Vert Aquaculture", country="France")
        load_demo(db, owner.id, team_emails="public")
    # oxygen-drop predictions straight away (trains the model first if there is none)
    with session_scope() as db:
        from .ml.predict import predict_all

        predict_all(db)
    print(f"Demo farm ready in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
