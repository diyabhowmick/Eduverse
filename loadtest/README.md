# Load test

Measures how many reading students a server can take. Use staging, never production.

1. Publish a real textbook and note its id. From `backend/`, with the server's environment:
   `python ../loadtest/prepare.py <book_id> 1500`
2. From the project folder, against the server:
   `EV_URL=https://staging.example.com python loadtest/loadgen.py real 600 90`
   `real N S`: N students reading with real pauses for S seconds. `max N S`: no pauses, to find the most requests a second.
3. Read p95 (95% of requests faster than this). Under 500 ms feels instant; over 2 s feels slow.
   Raise N until p95 passes 1 s: that is the number of students reading at once this setup takes.
