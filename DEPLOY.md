# Deploying MANAS

## 1. Run it locally (simplest — works today)

```bash
pip install -e .
cp .env.template .env       # optional; defaults run fully offline
manas status
manas chat
```

That's the whole thing. The kernel is pure Python + FastAPI — no build step, no GPU.

## 2. Run it as an always-on service

**Docker (recommended, portable):**
```bash
docker build -t manas:0.1.0 .
docker run -d -p 8420:8420 -v manas-data:/data \
  -e MANAS_PROVIDER=anthropic -e MANAS_ANTHROPIC_API_KEY=sk-... manas:0.1.0
curl localhost:8420/health
```

**Full local-first stack (MANAS + local LLM, zero cloud keys):**
```bash
docker compose up -d
docker compose exec ollama ollama pull llama3.1   # one-time model download
```

**systemd (laptop / home server / HPE SLES node):**
```bash
sudo cp -r . /opt/manas && cd /opt/manas
python3 -m venv .venv && .venv/bin/pip install -e .
sudo cp deploy/manas.service /etc/systemd/system/manas@$USER.service
sudo systemctl enable --now manas@$USER
```
(You already have this muscle memory from ATIQ's `setup-remote.sh` SLES deploy.)

## 3. Hardware — what you actually need

The **kernel itself is negligible**: runs on a Raspberry Pi, a laptop, anything.
It's I/O-bound Python. Hardware is entirely a function of *which provider* you pick:

| Provider    | Where inference runs | Hardware on your machine                    |
|-------------|----------------------|---------------------------------------------|
| `echo`      | nowhere (stub)       | none — runs anywhere                         |
| `anthropic` | Anthropic cloud      | none; needs internet + API key              |
| `copilot`   | GitHub cloud         | none; needs internet + `GITHUB_COM_TOKEN`   |
| `ollama`    | **your hardware**    | this is the only case where specs matter ▼  |

**Local inference (ollama) rough guide:**

| Model size        | RAM/VRAM      | Runs on…                                  |
|-------------------|---------------|-------------------------------------------|
| 3B (llama3.2)     | ~4–8 GB       | any modern laptop, CPU-only, usable       |
| 8B (llama3.1)     | ~8–16 GB      | laptop CPU (slow) or 8 GB+ GPU (fast)     |
| 70B               | 40 GB+ VRAM   | workstation / server with a real GPU      |

Practical answer: **run the kernel + a cloud provider on your laptop today** — no
special hardware. Add Ollama later on whatever machine has the RAM/GPU if you want
fully offline inference. The scaling invariant means the same code moves from
laptop → home server → SLES node → GPU box with only `.env` changes.

## 4. Where to keep the source

- **github.com private repo** — natural home for a general-purpose personal project.
  Free, and you own it outright.
- **github.hpe.com** — where ATIQ/VECTOR live, but those are HPE-internal tools.
  MANAS is general-purpose, so putting it there implies HPE context. See §5.
- **Self-hosted Gitea/GitLab** — fits the local-first philosophy if you'd rather
  not host it externally at all.

## 5. License — and the question to answer first

Common choices, factually:

- **MIT** — shortest, most permissive. Anyone can use/modify/sell; just keep the
  notice. Best if you want maximum adoption and don't care what people build.
- **Apache 2.0** — permissive like MIT *plus* an explicit patent grant. A safer
  default for anything that might touch patentable techniques.
- **GPLv3** — permissive to use, but derivatives must also be open-sourced
  ("copyleft"). Use if you want improvements to flow back.
- **No license** — default is *all rights reserved*; others legally can't reuse it.

**The prerequisite question (not legal advice — I'm not a lawyer):** you can only
license what you own. If MANAS was built on HPE equipment, on work time, or relates
closely to your role, your employment/IP agreement may give HPE a claim — the same
way ATIQ and VECTOR are HPE-internal. Before publishing under any open license,
worth a quick check of your HPE IP agreement or a word with your manager. If it's
cleanly your own personal project on your own time and gear, MIT or Apache 2.0 are
the usual picks.
