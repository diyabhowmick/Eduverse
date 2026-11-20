"""Runs one processing job in its own process: python -m app.jobrun <job id>. See routers/jobs.py supervise()."""
import sys
from .routers.jobs import run_m1

run_m1(int(sys.argv[1]))
