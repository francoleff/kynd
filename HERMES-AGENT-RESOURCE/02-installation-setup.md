# 02 : Getting set up

Ten minutes . Maybe twenty . No coding .

One path . Follow it top to bottom . Save the rest for later .

---

## Step 1 : Install

macOS , Linux , or WSL2 :

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Windows (PowerShell) :

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

The installer handles Python , Node , and everything else . You don't need to install anything first .

When it finishes , close the terminal and open a new one . That makes the `hermes` command available .

## Step 2 : Check the install

When its done downloading just say "hermes setup" in the terminal

## Step 3 : Give it a brain

Hermes needs a model to think with . The easiest way is Nous Portal . You can get a free subscription that gets you free ai models if you arent currently paying a subscription for one .

```bash
hermes setup --portal
```

A browser window opens . Log in . Grab the free subscription . That's it .

```bash
hermes portal info    # check your login , any time
```

## Step 4 : First conversation

```bash
hermes
```

You'll see a welcome banner with your model name on it . Then ask something simple :

```
Summarize this repository in 5 bullets and tell me what the main entrypoint is .
```

You're done when :

- The banner shows your model
- It used a tool when one was needed (file read , web search , ...)

Two commands to learn now :

- `/new` : fresh conversation
- `/usage` : what you've spent

## Step 5 : Done

- [ ] `which hermes` prints a path
- [ ] `hermes doctor` is healthy
- [ ] `hermes` opens without errors
- [ ] The banner shows your model
- [ ] Your first prompt got a real answer
- [ ] A tool worked when one was needed

That's it . You're running .

**NEXT →** [03 : UNDERSTANDING THE HARNESS](03-understanding-the-harness.md)

---

## Read later

### Other ways to get a model

#### Bring your own key

```bash
hermes model
```

Pick a provider , paste a key , pick a model . Keys live in `~/.hermes/.env` . Common ones :

| Provider | Env var |
|---|---|
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Google Gemini | `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) |
| DeepSeek | `DEEPSEEK_API_KEY` |
| xAI (Grok) | `XAI_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |
| Hugging Face | `HF_TOKEN` |

OpenRouter has some free models , check the current list on openrouter.ai first .

#### Local models (advanced)

Ollama , LM Studio , vLLM , llama.cpp . They work , but two rules : the model needs at least 64k of context , and local models need real hardware to be good . Start with cloud . Try local later .

#### Desktop app

Prefer an app over the terminal ? Grab the installer from <https://hermes-agent.nousresearch.com/> .

### Where things live (curious only)

You almost never touch these by hand . The commands do it for you :

- `~/.hermes/config.yaml` . Settings : model , provider , approvals
- `~/.hermes/.env` : API keys
- `~/.hermes/auth.json` : logins
- `~/.hermes/state.db` : every conversation

### Stuck ?

- `hermes: command not found` → new terminal , or `source ~/.bashrc` (macOS : `source ~/.zshrc`)
- "Python version too old" → Hermes needs Python 3.11+ . The installer handles it . Don't fight system Python .
- "Permission denied" → a previous sudo install . `sudo rm /usr/local/bin/hermes` , then re-run the installer .
- Antivirus flags `uv.exe` (Windows) → false positive . Whitelist the folder `%LOCALAPPDATA%\hermes\bin` .

Full list in section 08 .

---

Freshness : install URLs and OS support change with releases . Re-check the README . Provider pricing changes . Check before you pay .
