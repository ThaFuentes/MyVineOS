# MyChurch sandbox

Working copy of MyVineOS for the community layer (church page, Feed, optional member pages).

```bash
cd ~/pyprojects/myvinechurch.online/MyChurch
./myvineos
# always binds 0.0.0.0:5002 (this VM + Tailscale)
# http://127.0.0.1:5002
# http://<tailscale-ip>:5002   (launcher prints the real IP)
```

Own MariaDB on host port **3311**. Own session cookie. Does not use the parent `.env` or `myvinechurch-db`.

First run: Owner setup on :5002 — that Owner lives only in `mychurch_sandbox`.
