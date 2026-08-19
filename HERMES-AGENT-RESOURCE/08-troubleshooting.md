# 8. Troubleshooting

Same format everywhere : problem → likely cause → fix → how to verify .

Every fix comes from the official FAQ , README , or docs . Checked August 11 , 2026 . Where it's my judgment instead of a source , I say so .

- **Install:**
  - **1. `hermes: command not found` after install** . Cause : your shell hasn't reloaded the updated PATH .
    - Fix :
      ```bash
      source ~/.bashrc    # bash
      source ~/.zshrc     # zsh
      ```
      Or open a new terminal window .
    - Verify : `which hermes` returns a path (e.g. , `~/.local/bin/hermes`) , then `hermes doctor` .
  - **2. "Python version too old"** . Cause : Hermes needs Python 3.11+ .
    - Fix : don't fight system Python . The official installer provisions its own Python via `uv` . If you hand-installed , re-run the official one-liner from section 2 .
    - Verify : `hermes doctor` passes ; `hermes` opens .
  - **3. `node: command not found` (or nvm/pyenv/asdf) inside Hermes** . Cause : Hermes builds a per-session environment snapshot by running `bash -l` once at startup . It reads profile files but does not source `~/.bashrc` .
    - Fix : list extra files to source in `~/.hermes/config.yaml` :
      ```yaml
      terminal:
        shell_init_files:
          - ~/.zshrc
          - ~/.nvm/nvm.sh
          - /etc/profile.d/cargo.sh
      ```
    - Verify : inside Hermes , run `node --version` and get a version , not "command not found" .
  - **4. `uv: command not found`** . Cause : uv missing or not on PATH .
    - Fix :
      ```bash
      curl -LsSf https://astral.sh/uv/install.sh | sh
      source ~/.bashrc
      ```
    - Verify : `uv --version` prints a version .
  - **5. "Permission denied" during install** . Cause : a previous sudo install left files a per-user install can't touch .
    - Fix :
      ```bash
      sudo rm /usr/local/bin/hermes
      curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
      ```
    - Verify : install completes without errors ; `hermes doctor` is healthy .
  - **6. Windows : antivirus quarantines `uv.exe`** . Cause : false positive . ML antivirus engines flag unsigned Rust binaries (this is Astral's `uv` , bundled by Hermes) .
    - Fix : whitelist the folder , not the file hash (the hash changes every version) :
      - Windows Defender : PowerShell as Admin → `Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\hermes\bin"`
      - Bitdefender : add an exception for the folder
    - Verify : install completes ; `hermes doctor` passes . The README documents a full hash-verification flow if you want proof the binary is authentic .

- **Providers and models:**
  - **7. `/model` only shows one provider** . Cause : in-session `/model` can only reach providers you've already configured .
    - Fix : exit the session (Ctrl+C or `/quit`) and run `hermes model` from your terminal to add a provider or key .
    - Verify : `/model` in a new session lists the new provider .
  - **8. "API key not working"** . Cause : key missing , expired , wrong provider , or saved in the wrong file .
    - Fix : check `hermes config show` (or `hermes config get <key>`) , re-run `hermes model` to paste the key again . Keys live in `~/.hermes/.env` .
    - Verify : a fresh prompt gets a reply instead of an auth error .
  - **9. "Model not available / model not found"** . Cause : the model identifier is wrong or unavailable on your provider .
    - Fix : run `hermes model` to list what's actually available , pick from the list .
    - Verify : `/status` shows the correct model and provider .
  - **10. Rate limiting (429 errors)** . Cause : you exceeded the provider's rate limit .
    - Fix : wait and retry , upgrade the plan , or switch model or provider .
    - Verify : the same prompt succeeds on retry .
  - **11. "Context length exceeded"** . Cause : the conversation outgrew the context window (or Hermes detected the wrong one) .
    - Fix : `/compress` (summarizes history) , start a fresh session , or set context explicitly :
      ```yaml
      model:
        default: your-model-name
        context_length: 131072
      ```
    - Verify : the next turn succeeds without a context error .
  - **12. Local model (Ollama) context overflow** . Cause : Ollama reports the model's max theoretical window , not your effective `num_ctx` . Hermes thinks it has more room than it does .
    - Fix : match your Ollama `num_ctx` setting explicitly in Hermes config (`model.context_length`) .
    - Verify : long multi-step tasks stop dying with context errors .
  - **13. The agent refuses , claiming "Hermes policy" or "Hermes guardrails"** . Cause : models can't reliably explain their own refusals . If the refusal only shows in prose (not as an explicit tool error or approval prompt) , the "policy" explanation is likely hallucinated . The restriction comes from the model or provider , not a hidden Hermes filter .
    - Fix : run `/status` to confirm the active model ; retry in a fresh session with another configured model if needed .
    - Verify : the refusal changes or disappears with a different model . And you never see a hidden-Hermes-policy error in tool output .
  - **14. Sudden cost jump after switching models mid-session** . Cause : switching models mid-conversation resets the prompt cache . The next turn re-reads the whole history at full price .
    - Fix : pick a model and stay on it for the session ; use `/compress` to shrink history before switching . (My call , not the docs . It's the sane habit .)
    - Verify : `/usage` shows normal cached-token pricing on subsequent turns .

- **Messaging gateway:**
  - **15. `sudo` password prompts fail from Telegram or Discord** . Cause : the gateway runs a non-interactive background process . Interactive password entry can't happen .
    - Fix : configure passwordless execution for the specific command , or run that task from the CLI where you can approve interactively .
    - Verify : the command runs from CLI (with approval) , and from the gateway only when it no longer needs a password .
  - **16. Unknown users can message the bot** . Cause : no allowlist or pairing configured .
    - Fix : set platform allowlists (`TELEGRAM_ALLOWED_USERS` , `DISCORD_ALLOWED_USERS` , etc.) or use DM pairing (`hermes pairing approve telegram <CODE>`) . Never set `GATEWAY_ALLOW_ALL_USERS=true` on an agent with terminal access .
    - Verify : a second account can no longer reach the bot .

- **Safety net:**
  - **17. "I let it run and it changed things I didn't want"** . Cause : approvals misconfigured (`approvals.mode: off` or repeated "always") , or no checkpoints .
    - Fix :
      ```yaml
      approvals:
        mode: smart        # default ; or "manual" for max caution
      checkpoints:
        enabled: true
      ```
      Then undo : in chat , `/rollback` lists snapshots ; `/rollback <N>` restores .
    - Verify : `hermes checkpoints` shows your store ; `/rollback` lists a snapshot from before the change .

- **Quick index:**

  | Symptom | Entry |
  |---|---|
  | Command not found (any tool) | 1 , 3 , 4 |
  | Install permission errors | 5 |
  | Antivirus quarantine | 6 |
  | Model / provider issues | 7-10 |
  | Context / length issues | 11 , 12 |
  | Weird refusals | 13 |
  | Cost surprises | 14 |
  | Gateway / phone access | 15 , 16 |
  | Undo damage | 17 |

Not here ? Two moves : `hermes doctor` (diagnostics) and the official FAQ . New issues : report them in the Kynd Discord . Verified fixes get added here with credit .
