"""A worker container: python -m app.worker. Runs queued background work (book reading, explanations, papers)."""
from .db import engine
from .models import Base


if __name__ == "__main__":
    from .hardening import check_config
    check_config()
    Base.metadata.create_all(engine)
    from . import tasks
    print(f"[EV TASKS] worker {tasks.WORKER_ID} started", flush=True)
    tasks.loop()
