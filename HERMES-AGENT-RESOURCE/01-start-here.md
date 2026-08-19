# 1. Introduction & Hermes Agent Philosophy

Welcome

This is the resource I wish I had when I started working with this powerful technology .

- **What is Hermes Agent?** An open-source AI agent harness from Nous Research . Plain words : it's a program that runs an AI agent in your terminal and gives it hands . Web search . Files . Terminal . Browser . It works on its own , remembers across sessions , and learns skills as it goes . It's like an employee that constantly learns and improves .

- **Model vs. Harness:** First thing to get straight : this is not the "Hermes" models . Nous makes both . The harness is the machine . The models are the brains . You can plug any model from any provider into it .

- **Self-Improvement Loop:** Learns skills from experience . It creates skills on its own and improves them while it works . That "learns from experience" part is the point .

- **Memory Curation:** Remembers across sessions . Memory files plus full-text search over every past conversation .

- **What it can actually do:**
  - Runs a full agent in your terminal .
  - 60+ built-in tools . Web search , files , terminal , browser , image generation , text to speech .
  - Talks to you anywhere . CLI plus 20+ platforms , Telegram , Discord , Slack , WhatsApp , Signal , Email , through one gateway .
  - Runs on a schedule . Built-in cron . "Every Monday , write me a briefing ." Real sentence .
  - Delegates . Spawns isolated subagents that work in parallel and report back .
  - Uses any model . Nous Portal , OpenRouter , OpenAI , Anthropic , Google , DeepSeek , or a local model . Switch with `hermes model` .
  - Connects to anything via MCP . Databases , GitHub , your own APIs .
  - Undoes mistakes . Checkpoints plus `/rollback` before destructive operations .

  All of that is checked against the official docs and repo . August 11 , 2026 .

- **Who this is for:**
  - If you want an AI that does things instead of one that just chats
  - If you're a beginner : sections 1-5 need zero coding .
  - If you want an assistant that remembers you .
  - If you learn by using , not by watching slides .

- **What you'll build:**
  - Build 1 : The Research Brief Agent . Section 4 . Researches topics and writes briefs to files .
  - Build 2 : The Research Agent . Section 6 . Build 1 , expanded into a tool you actually rely on .
  - Build 3 : The Personal Assistant . Section 6 . One you text from your phone .
  - Build 4 : The Content System . Section 6 . Ideas in , structured drafts out .
  - Build 5 : The Business Operations Agent . Section 6 . Scheduled , delegated ops .
  - Build 6 : The Multi-Agent Workflow . Section 6 . Several specialists , one task board .

- **Prerequisites:** A computer . That's it .

- **How hard is this:**
  - Install and first chat : easy . One command , then `hermes` .
  - Portal setup : easy . One command , browser login .
  - Local models : medium . Save that for later .

---

**Next →** [2 : INFRASTRUCTURE SETUP & HARDWARE OPTIONS](02-installation-setup.md)
